"""
The assessment domain: certifications, bookings, and — as they arrive — exam
versions, sections, questions, attempts, responses, grading, and credentials.

These belong together because they constrain one another: an attempt references a
frozen exam version, a credential references the attempt that earned it.

Dependencies point one way. This app references the user through
``settings.AUTH_USER_MODEL`` (a string, so no import); ``apps.home`` may import
from here, never the reverse.

If this file grows past a few hundred lines, split it into a ``models/`` package
re-exported from ``models/__init__.py`` — not into another app.
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

class Question(models.Model):
    """
    A question is a single question in an exam.
    """
    class Difficulty(models.TextChoices):
        EASY = "easy", "Easy"
        MEDIUM = "medium", "Medium"
        HARD = "hard", "Hard"

    class Type(models.TextChoices):
        OBJECTIVE = "objective", "Objective"
        SUBJECTIVE = "subjective", "Subjective"

    question_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="questions")
    question_type = models.CharField(max_length=16, choices=Type.choices, default=Type.OBJECTIVE)
    question_difficulty = models.CharField(max_length=16, choices=Difficulty.choices, default=Difficulty.EASY)
    question_subject = models.ForeignKey("Subject", on_delete=models.PROTECT, related_name="questions")
    associated_image = models.ForeignKey("Image", on_delete=models.PROTECT, related_name="questions", blank=True, null=True)
    associated_audio = models.ForeignKey("Audio", on_delete=models.PROTECT, related_name="questions", blank=True, null=True)
    associated_video = models.ForeignKey("Video", on_delete=models.PROTECT, related_name="questions", blank=True, null=True)
    question_keywords = models.TextField(blank=True)
    question_tags = models.TextField(blank=True)
    marks = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "questions"
        ordering = ["-created_at"]

class AnswerOptions(models.Model):
    """
    Options that will be provided in objective questions.
    """
    answer_option_text = models.TextField()
    is_correct = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="answers")

class Audio(models.Model):
    """
    An audio file is a file that contains audio. It is associated with a question.
    """
    audio_file = models.FileField(upload_to="audio/")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="audios")

class Image(models.Model):
    """
    An image file is a file that contains an image. It is associated with a question.
    """
    image_file = models.FileField(upload_to="image/")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="images")

class Video(models.Model):
    """
    A video file is a file that contains video. It is associated with a question.
    """
    video_file = models.FileField(upload_to="video/")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="videos")

class Subject(models.Model):
    """
    A subject is a subject of study for which a candidate can take an exam.
    """
    class Level(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True) 
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="subjects")
    subject_level = models.CharField(max_length=16, choices=Level.choices, default=Level.BEGINNER)

    class Meta:
        db_table = "subjects"
        ordering = ["name"]
    
    def __str__(self):
        return self.name

class Exam(models.Model):
    """
    An exam entity that can be taken by a candidate.
    """
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    class Type(models.TextChoices):
        OBJECTIVE = "objective", "Objective"
        SUBJECTIVE = "subjective", "Subjective"
    #: Duration is determined by the exam type. Single source of truth — the
    #: CheckConstraint in Meta mirrors these values, so change both together.
    DURATION_BY_TYPE = {
        Type.OBJECTIVE: 45,
        Type.SUBJECTIVE: 36 * 60,  # 36 hours
    }
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="exams")
    exam_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Defaults to '<subject> Certification Exam' when left blank.",
    )
    candidate_name = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="exams")
    #: Mirrors the slug the main site already uses in its catalog URLs
    #: (testmuai.com/certifications/<slug>/). Internal, but keeping them aligned
    #: gives both systems one vocabulary.
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    marketing_url = models.URLField(blank=True)

    #: TestMu AI's own numeric course id, as passed by the current redirect
    #: (?id=2934). Nullable and unused for now — it exists so a prefill hint can
    #: be mapped later without a migration.
    external_ref = models.CharField(max_length=64, blank=True, null=True, db_index=True)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)

    exam_type = models.CharField(max_length=16, choices=Type.choices, default=Type.OBJECTIVE)

    #: Minutes, per repo convention that durations state their unit. Set from
    #: `type` — leave it blank and save() fills it in.
    duration_minutes = models.PositiveIntegerField(
        help_text="Determined by the exam type: 45 for objective, 2160 (36h) for subjective."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    scheduled_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "exams"
        ordering = ["scheduled_at"]
        constraints = [
            # The database refuses a mismatched pair no matter how the row is
            # written — admin, shell, bulk_create, or raw SQL. clean() and
            # save() are conveniences; this is the guarantee.
            models.CheckConstraint(
                condition=(
                    models.Q(exam_type="objective", duration_minutes=45)
                    | models.Q(exam_type="subjective", duration_minutes=36 * 60)
                ),
                name="exam_duration_matches_type",
            ),
        ]

    def __str__(self):
        return self.exam_name

    @property
    def level(self):
        """Level comes from the subject — one source of truth."""
        return self.subject.subject_level

    def get_level_display(self):
        return self.subject.get_subject_level_display()

    def clean(self):
        """Form-level validation — gives a readable error instead of IntegrityError."""
        super().clean()
        expected = self.DURATION_BY_TYPE.get(self.exam_type)
        if expected is None:
            raise ValidationError({"type": "Unknown exam type."})
        if not self.duration_minutes:
            self.duration_minutes = expected
        elif self.duration_minutes != expected:
            raise ValidationError(
                {
                    "duration_minutes": (
                        f"{self.get_exam_type_display()} exams must be {expected} minutes."
                    )
                }
            )

    def save(self, *args, **kwargs):
        # Fill in derived values for callers that skip full_clean() — the shell,
        # scripts, the seed command.
        if not self.exam_name and self.subject_id:
            self.exam_name = f"{self.subject.name} Certification Exam"
        if not self.duration_minutes:
            self.duration_minutes = self.DURATION_BY_TYPE[self.exam_type]
        super().save(*args, **kwargs)


class ExamBooking(models.Model):
    """
    Self-scheduled, not slot-based: candidates pick their own date and time.
    There are no pre-defined slots and no capacity, so there is no seat
    contention — the concurrency problem that would otherwise dominate booking
    does not exist.
    """

    class Status(models.TextChoices):
        BOOKED = "booked", "Booked"
        CANCELLED = "cancelled", "Cancelled"
        ATTENDED = "attended", "Attended"
        NO_SHOW = "no_show", "No show"

    #: Nullable until the OIDC integration lands — see archived/docs/auth.md.
    #: Every booking must have a candidate before this reaches real users.
    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bookings",
        null=True,
        blank=True,
    )
    booking_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    exam = models.ForeignKey(Exam, on_delete=models.PROTECT, related_name="bookings")

    #: Stored UTC. Always.
    scheduled_at = models.DateTimeField()

    #: The IANA zone the candidate booked in. Kept alongside the instant because
    #: it is what reminders display, and what you reason about if someone
    #: disputes the time.
    booked_timezone = models.CharField(max_length=64)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.BOOKED)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bookings"
        ordering = ["-scheduled_at"]
        constraints = [
            # One open booking per exam per candidate. Partial, so a
            # cancelled booking doesn't block rebooking.
            models.UniqueConstraint(
                fields=["candidate", "exam"],
                condition=models.Q(status="booked"),
                name="one_open_booking_per_exam",
            ),
        ]

    def __str__(self):
        return f"{self.exam} @ {self.scheduled_at:%Y-%m-%d %H:%M} UTC"

    @property
    def local_scheduled_at(self):
        from .timezones import to_local

        return to_local(self.scheduled_at, self.booked_timezone)
