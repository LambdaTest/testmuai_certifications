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

import math
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.core.validators import (FileExtensionValidator, MaxValueValidator,
                                    MinValueValidator)

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

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RETIRED = "retired", "Retired"

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
    question_tags = models.TextField(blank=True)
    marks = models.PositiveIntegerField(default=5)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)

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
    associated_image = models.ForeignKey("Image", on_delete=models.PROTECT, related_name="answers", blank=True, null=True)
    associated_audio = models.ForeignKey("Audio", on_delete=models.PROTECT, related_name="answers", blank=True, null=True)

    #: Where this option appears in the list, 1-based, in the order the author
    #: wrote it. Without it, options come back in whatever order Postgres
    #: returns, and that order can differ between two reads of the same rows —
    #: so a candidate could watch the answers rearrange between page loads.
    #:
    #: Assigned by BaseAnswerOptionFormSet.save(), which numbers the filled
    #: slots as they were submitted. Both the authoring page and the CSV
    #: importer go through that formset, so the form's top-to-bottom order and
    #: the option_1..option_6 column order land the same way.
    #:
    #: Defaulted to 0 rather than made required, because rows written before
    #: this column existed have no order to recover. They sort first, together,
    #: which is no worse than the arbitrary order they had.
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        # No db_table here, unlike the other models in this file. Setting one
        # now would rename a table that already holds rows — a change worth
        # making deliberately, not as a side effect of adding a column.
        ordering = ["position"]


class Audio(models.Model):
    """
    An audio file is a file that contains audio. It is associated with a question.
    """
    audio_file = models.FileField(upload_to="audio/", validators=[FileExtensionValidator(["mp3", "wav", "m4a", "ogg"])])
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="audios")

class Image(models.Model):
    """
    An image file is a file that contains an image. It is associated with a question.
    """
    image_file = models.FileField(upload_to="image/", validators=[FileExtensionValidator(["png", "jpg", "jpeg", "gif", "webp"])])
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="images")

class Video(models.Model):
    """
    A video file is a file that contains video. It is associated with a question.
    """
    video_file = models.FileField(upload_to="video/", validators=[FileExtensionValidator(["mp4", "webm"])])
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="videos")

class Subject(models.Model):
    """
    A subject is a subject of study for which a candidate can take an exam.
    """
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True) 
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="subjects")

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
        BOTH = "both", "Both"
    #: Duration is determined by the exam type. Single source of truth — the
    #: CheckConstraint in Meta mirrors these values, so change both together.
    DURATION_BY_TYPE = {
        Type.OBJECTIVE: 45,
        Type.SUBJECTIVE: 36 * 60,  # 36 hours
        #: Both rounds end to end: the 45-minute objective sitting plus the
        #: 36-hour subjective window. Written as a sum so it reads as the two
        #: rounds it is, and so it matches the CheckConstraint below character
        #: for character.
        #:
        #: It excludes the 30-minute cooling period between the rounds, and it
        #: is a TOTAL FOR DISPLAY — not a schedulable span. The rounds are
        #: separate sittings with their own clocks, held on separate bookings,
        #: so nothing should reserve 2205 continuous minutes of a candidate's
        #: time. occupied_minutes() in forms.py is the place that matters.
        Type.BOTH: 45 + 36 * 60,  # 2205
    }
    class Level(models.TextChoices):
            BEGINNER = "beginner", "Beginner"
            INTERMEDIATE = "intermediate", "Intermediate"
            ADVANCED = "advanced", "Advanced"

    class QuestionSelection(models.TextChoices):
      RANDOM = "random", "Randomize From Pool"
      MANUAL = "manual", "Select Manually"

    #: Every objective question is worth the same, as on Eklavya. That uniformity
    #: is what makes a random draw safe to set an absolute pass mark against: a
    #: paper of N questions always totals N × 5, whoever sits it.
    MARKS_PER_QUESTION = 5

    #: A subjective round is one question. A constant rather than a field
    #: because every exam we have uses one — a nullable column would be a
    #: migration, a form input and a branch, all carrying a number nobody
    #: varies. One line to change if that stops being true.
    SUBJECTIVE_QUESTION_COUNT = 1

    #: What that one subjective question is worth. Far more than an objective
    #: question, because it is a scenario answer an examiner reads rather than
    #: a choice among four — and because a round given 36 hours has to matter
    #: to the total or nobody will sit it.
    SUBJECTIVE_MARKS = 50

    #: Share of the paper needed to pass when an author does not say otherwise.
    #: A house rule, so it lives beside the other two rather than as a bare 70
    #: on the field below. Whole percent, matching what pass_percentage stores.
    DEFAULT_PASS_PERCENTAGE = 70

    question_selection = models.CharField(max_length=30, choices=QuestionSelection.choices, default=QuestionSelection.RANDOM)
    #: Random draws only — how many to pull from the subject's bank. Null for a
    #: manual paper, where the questions are chosen rather than counted.
    question_count = models.PositiveIntegerField(null=True, blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="exams")
    exam_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Defaults to '<subject> Certification Exam' when left blank.",
    )
    # candidate_name = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="exams")
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
    exam_level = models.CharField(max_length=16, choices=Level.choices, default=Level.BEGINNER)
    #: Minutes, per repo convention that durations state their unit. Set from
    #: `type` — leave it blank and save() fills it in.
    duration_minutes = models.PositiveIntegerField(
        help_text="Determined by the exam type: 45 for objective, 2160 (36h) for subjective."
    )
    #: TEMPORARY as a stored field. Once Exam ↔ Question exists this becomes a
    #: derived property — the sum of the per-exam marks — because a stored total
    #: silently goes stale the moment a question is added, removed or reweighted.
    #: Nothing should write to it once that relation lands.
    maximum_marks = models.PositiveIntegerField(blank=True, null=True)

    #: Share of the paper needed to pass, as a whole percentage.
    #:
    #: A percentage, not absolute marks, because a paper's total is not fixed.
    #: A subjective round draws one question from a pool whose questions differ
    #: in weight, so two candidates can sit papers worth different totals — and
    #: "35 marks to pass" then means different things to each of them. 70% means
    #: the same thing to both.
    #:
    #: An integer rather than a float: authors type 70, not 0.7, and a small
    #: integer cannot accumulate the rounding error a float can.
    #:
    #: The absolute figure is derived — see pass_mark — and snapshotted onto the
    #: booking when the paper is drawn, so raising the bar later never
    #: reclassifies a credential already issued.
    pass_percentage = models.PositiveSmallIntegerField(
        default=DEFAULT_PASS_PERCENTAGE,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Whole percent of the paper needed to pass.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="exams", null=True)
    # scheduled_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "exams"
        ordering = ["updated_at"]
        constraints = [
            # The database refuses a mismatched pair no matter how the row is
            # written — admin, shell, bulk_create, or raw SQL. clean() and
            # save() are conveniences; this is the guarantee.
            models.CheckConstraint(
                condition=(
                    models.Q(exam_type="objective", duration_minutes=45)
                    | models.Q(exam_type="subjective", duration_minutes=36 * 60)
                    | models.Q(exam_type="both", duration_minutes=45 + 36 * 60)
                ),
                name="exam_duration_matches_type",
            ),
            # The objective count belongs to the objective round, so a
            # subjective-only exam must not carry one and the other two must.
            #
            # ExamForm.clean() says the same thing with a readable message and
            # the template hides the input — but neither reaches the admin, the
            # shell, bulk_create or a hand-made post. This is the guarantee; the
            # others are the explanation.
            #
            # An exam with no count and no rule against it would look bookable
            # and then fail at Start Test, when a candidate is sitting in front
            # of it — the worst moment to discover a paper cannot be drawn.
            models.CheckConstraint(
                condition=(
                    models.Q(exam_type="subjective", question_count__isnull=True)
                    | (
                        ~models.Q(exam_type="subjective")
                        & models.Q(question_count__isnull=False)
                    )
                ),
                name="exam_question_count_matches_type",
            ),
        ]

    @staticmethod
    def _humanise_minutes(minutes):
        """45 -> "45 min"; 2160 -> "36 hrs". Whole hours only, since every
        round we have is either well under an hour or an exact number of them."""
        if minutes >= 60 and minutes % 60 == 0:
            hours = minutes // 60
            return f"{hours} hr{'' if hours == 1 else 's'}"
        return f"{minutes} min"

    @property
    def duration_display(self):
        """
        How long this exam takes, phrased for a candidate: "45 min", "36 hrs",
        or "45 min + 36 hrs".

        A two-round exam is not 2205 continuous minutes and printing it that way
        is true but useless — it reads as a 37-hour sitting. The rounds are what
        a candidate plans around, so the rounds are what this names.

        Built by asking each round whether it applies, the same shape as
        total_marks_for(), and off DURATION_BY_TYPE rather than repeating the
        numbers. Five templates used to carry their own `== 2160` check; this
        is what replaces them.
        """
        parts = []
        if self.exam_type != self.Type.SUBJECTIVE:
            parts.append(self._humanise_minutes(self.DURATION_BY_TYPE[self.Type.OBJECTIVE]))
        if self.exam_type != self.Type.OBJECTIVE:
            parts.append(self._humanise_minutes(self.DURATION_BY_TYPE[self.Type.SUBJECTIVE]))
        return " + ".join(parts)

    @property
    def pass_mark(self):
        """
        The pass mark in marks, derived from the percentage and the projected
        total. None when the total is unknown.

        A projection, not a promise, for any exam with a subjective round: the
        real figure depends on which question that candidate draws, and is
        snapshotted onto their booking when the paper is built. For a purely
        objective exam the two are always equal, since every question is worth
        MARKS_PER_QUESTION.

        ceil rather than round, so a 250-mark paper at 70% needs 175 and a
        249-mark one needs 175 rather than 174 — the bar never rounds down.
        """
        if not self.maximum_marks:
            return None
        return math.ceil(self.maximum_marks * self.pass_percentage / 100)

    def __str__(self):
        return self.exam_name

    @classmethod
    def total_marks_for(cls, exam_type, question_count):
        """
        What a paper is out of, for an exam of this shape.

            objective   count × 5
            subjective            50
            both        count × 5 + 50

        Each round contributes or contributes nothing, and the total is the
        sum — so no format is a special case and adding a third round later
        would be a third term rather than a rewrite.

        Takes `exam_type`, not `question_selection`, since selection stopped
        being a choice: every paper is a random draw now.

        A classmethod rather than a property because ExamForm needs the answer
        for values just submitted, before they are on an instance. Both callers
        share this one definition, so the form and the database cannot disagree
        about the total.
        """
        objective = (
            0 if exam_type == cls.Type.SUBJECTIVE
            else (question_count or 0) * cls.MARKS_PER_QUESTION
        )
        subjective = (
            0 if exam_type == cls.Type.OBJECTIVE
            else cls.SUBJECTIVE_MARKS
        )
        return objective + subjective

    def clean(self):
        """Form-level validation — gives a readable error instead of IntegrityError."""
        super().clean()
        expected = self.DURATION_BY_TYPE.get(self.exam_type)
        if expected is None:
            # Keyed to the real field name. ModelForm._post_clean bridges model
            # errors onto the form by name and raises ValueError for one it does
            # not recognise — so a wrong key here is a 500, not a message.
            raise ValidationError({"exam_type": "Unknown exam type."})
        # Overwritten, never rejected. Duration is derived from the type and has
        # no input anywhere, so a mismatch can only mean the type just changed —
        # and the right answer to that is the new duration, not an error.
        #
        # It used to raise here, keyed to "duration_minutes". That field is not
        # on ExamForm, and _post_clean turns a model error naming an unknown
        # field into ValueError rather than a message — so every edit that
        # changed the type was a 500. The comment above about keying errors to
        # real form fields was written about the branch above this one; this
        # branch is why the rule matters.
        self.duration_minutes = expected

    def save(self, *args, **kwargs):
        # Fill in derived values for callers that skip full_clean() — the shell,
        # scripts, the seed command.
        if not self.exam_name and self.subject_id:
            self.exam_name = f"{self.subject.name} Certification Exam"
        if not self.duration_minutes:
            self.duration_minutes = self.DURATION_BY_TYPE[self.exam_type]
        # Maximum marks is derived, never typed. Guarded on None so saving a
        # manual exam doesn't wipe a total that was set some other way — for
        # manual papers the helper has no source to work from yet.
        # Always a number now — every format has a total — so the None guard
        # that existed for manual papers is gone with manual selection.
        self.maximum_marks = self.total_marks_for(self.exam_type, self.question_count)
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
        UNDER_REVIEW = "under_review", "Under review"
        GRADED = "graded", "Graded"

    #: Nullable until the OIDC integration lands — see docs/auth.md.
    #: Every booking must have a candidate before this reaches real users.
    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bookings",
        null=True,
        blank=True,
    )
    booking_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    #: Which round of the exam this booking is for.
    #:
    #: A booking is one sitting, not one certification. An exam whose format is
    #: `both` produces two bookings — objective first, then a subjective one
    #: created when the objective is submitted. Single-format exams produce one.
    #:
    #: Stored rather than derived. The exam's format cannot answer it: Demo3 is
    #: subjective-only, so its single booking has no parent and is still a
    #: subjective round. Deriving would mean reading the format *and* the parent
    #: at every use, which is what this field exists to stop.
    round_type = models.CharField(
        max_length=16,
        choices=Exam.Type.choices,
        default=Exam.Type.OBJECTIVE,
    )

    #: The objective booking this subjective round belongs to. Null on a first
    #: round, which is how a first round is recognised.
    #:
    #: Held on the child, not the parent, so the column is filled the moment the
    #: row exists — a link on the objective booking would sit null for the whole
    #: life of every single-round exam.
    #:
    #: OneToOne rather than ForeignKey: a booking has at most one subjective
    #: follow-up, and a plain FK would permit five.
    #:
    #: This is what makes two rows one attempt, and grading needs exactly that —
    #: the pass mark is 70% of both rounds together. It could in principle be
    #: reconstructed from timestamps, since a subjective round starts 30 minutes
    #: after its objective was submitted. It should not be: the candidate can
    #: reschedule a booking, an admin can extend one, and the 30 minutes is a
    #: house rule that may change — any of which silently breaks the arithmetic.
    #: The handler that creates this row is holding both bookings already, so
    #: recording which is cheaper than re-deriving it forever.
    parent_booking = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        related_name="subjective_booking",
        blank=True,
        null=True,
    )
    exam = models.ForeignKey(Exam, on_delete=models.PROTECT, related_name="bookings")

    #: Stored UTC. Always.
    scheduled_at = models.DateTimeField()

    #: The IANA zone the candidate booked in. Kept alongside the instant because
    #: it is what reminders display, and what you reason about if someone
    #: disputes the time.
    booked_timezone = models.CharField(max_length=64)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.BOOKED)
    #: Null until graded — not a sentinel like -1, so aggregates such as an
    #: average score exclude ungraded bookings automatically.
    marks_obtained = models.PositiveIntegerField(blank=True, null=True)

    #: Snapshots of the exam's values, written at grading time, never read live.
    #: The exam keeps evolving — questions get added, reweighted or removed —
    #: so without the copies "82 out of 100" quietly becomes "82 out of 105",
    #: and a later change to the pass bar would reclassify old results.
    #: Together with marks_obtained these are all pass/fail needs.
    maximum_marks = models.PositiveIntegerField(blank=True, null=True)
    passing_marks = models.PositiveIntegerField(blank=True, null=True)
    graded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="graded_bookings", blank=True, null=True)
    graded_at = models.DateTimeField(blank=True, null=True)
    feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bookings"
        ordering = ["-scheduled_at"]
        constraints = [
            # One in-flight booking per exam per candidate. Partial: these
            # three states hold the slot; cancelled, no-show and graded release
            # it, so a candidate can book the exam again afterwards.
            #
            # String literals rather than Status.BOOKED — a class body is not
            # an enclosing scope, so names defined on ExamBooking are not
            # visible inside Meta.
            # round_type is part of the key, not an afterthought. A two-round
            # exam is two bookings for the same (candidate, exam) pair, so
            # without it the constraint refuses the subjective round the moment
            # the objective one is created — or, worse, appears to work only
            # because the objective row leaves this status set first, which
            # makes correctness depend on ordering rather than on the rule.
            models.UniqueConstraint(
                fields=["candidate", "exam", "round_type"],
                condition=models.Q(status__in=["booked", "under_review", "attended"]),
                name="one_open_booking_per_exam",
            ),
        ]

    def __str__(self):
        return f"{self.exam} @ {self.scheduled_at:%Y-%m-%d %H:%M} UTC"

    @property
    def stage(self):
        """
        Where an open booking sits against the clock: "upcoming", "underway" or
        "lapsed". None for any other status, which already describes itself.

        Status alone cannot answer this. A booking stays BOOKED until something
        changes it, and nothing does — NO_SHOW exists in Status and is never
        set, because the job that would set it is the Celery work that is not
        wired up yet. So a page labelling itself from `status` says "Upcoming"
        about an exam that finished last week.

        Derived rather than stored, deliberately. A stored value would need the
        same missing job to keep it true, and would then be wrong in the
        database rather than only on screen.

        "lapsed" is a display word, not a verdict. Whether a candidate may still
        start late — and whether the paper then runs a full duration or only to
        the original end — is an open decision in docs/master-spec.md. Nothing
        here forecloses it.
        """
        if self.status != self.Status.BOOKED:
            return None

        from django.utils import timezone as dj_tz

        now = dj_tz.now()
        if now < self.scheduled_at:
            return "upcoming"
        if now < self.scheduled_at + timedelta(minutes=self.exam.duration_minutes):
            return "underway"
        return "lapsed"

    @property
    def local_scheduled_at(self):
        from .timezones import to_local

        return to_local(self.scheduled_at, self.booked_timezone)

class Certificates(models.Model):
    """
    A certificate is a credential that a candidate earns by passing an exam.
    """
    certificate_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    certificate_file = models.FileField(upload_to="certificates/")
    booking = models.OneToOneField(ExamBooking, on_delete=models.PROTECT, related_name="certificate")

    class Meta:
        db_table = "certificates"
        ordering = ["-issued_at"]


class ExamSheet(models.Model):
    """
    The paper one candidate actually sat: the questions drawn for them, in the
    order they were shown, plus their answers.

    Created when they press Start Test, never at booking. Between booking and
    sitting the bank changes — questions get added and retired — and a paper
    fixed weeks ahead could hand somebody a question that has since been pulled.

    Fixing the paper at the start is also what makes a reconnect safe. A
    candidate whose connection drops comes back to the same twenty questions in
    the same order, at the position they left, with the same deadline. Drawing
    questions lazily as they press Next would re-randomise on a reload, make
    "question 3 of 20" a promise we cannot keep, and turn a double-clicked Next
    into a race.

    Results are not here. ExamBooking already carries marks_obtained,
    maximum_marks, passing_marks, graded_by, graded_at and feedback; a second
    home for a score is a second answer to "did they pass".
    """

    booking = models.OneToOneField(
        ExamBooking,
        on_delete=models.PROTECT,
        related_name="sheet",
    )

    started_at = models.DateTimeField(auto_now_add=True)

    #: When the paper closes. Stored rather than derived from started_at, so
    #: granting extra time to a candidate whose connection failed is an update
    #: to one column rather than a special case wherever the deadline is read.
    #:
    #: The server owns this. A deadline the browser can report is a deadline a
    #: candidate can extend.
    expires_at = models.DateTimeField()

    #: Which question the candidate is on, 1-based. Their bookmark, nothing to
    #: do with the questions themselves — a reconnect resumes here instead of
    #: starting again.
    #:
    #: Explicit rather than inferred from "first unanswered", because a
    #: candidate who deliberately skips question 3 to come back to it would
    #: otherwise be thrown backwards on every reload.
    current_position = models.PositiveSmallIntegerField(default=1)

    #: Null while the sitting is open; set when it ends, however it ends.
    #:
    #: One timestamp rather than a state machine, on purpose. Pressing Submit,
    #: running out of time and being stopped by an admin are all just "this
    #: paper is finished", and the score is the same in each case.
    #:
    #: Set it with min(timezone.now(), expires_at). For a normal submit that is
    #: a no-op; for a paper abandoned at 10:00 and swept up at 14:00 it records
    #: the exam as ending when it actually did.
    submitted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "exam_sheets"
        ordering = ["-started_at"]

    def __str__(self):
        return f"Sheet for {self.booking}"

    @property
    def is_open(self):
        """Whether answers may still be written to this sheet."""
        return self.submitted_at is None


class ExamSheetQuestion(models.Model):
    """
    One question as served to one candidate, and what they answered.

    The row is both the question slot and the response. A response cannot exist
    without the question having been served, so a separate Response model would
    only add a join.

    No snapshot of the question text. Questions are immutable by design — the
    Question Bank has no edit page — so the foreign key always resolves to what
    the candidate saw, and PROTECT means the row can never be deleted out from
    under a past paper. The one hole left is media: replacing the file on an
    Image row would change what an old paper appears to have shown. Tracked
    separately; the fix is to treat media rows as immutable too.
    """

    sheet = models.ForeignKey(
        ExamSheet,
        on_delete=models.CASCADE,
        related_name="questions",
    )

    #: PROTECT, and this is what makes deleting a served question impossible at
    #: the database level rather than only in a view. A question a candidate has
    #: been asked is the record of what they were asked; grading and appeals
    #: rest on it. Questions never served stay freely deletable.
    question = models.ForeignKey(
        Question,
        on_delete=models.PROTECT,
        related_name="sheet_entries",
    )

    #: Where this question sits on the paper, 1-based. Fixed at Start Test, so
    #: the order cannot change under a candidate between page loads.
    #:
    #: There is no equivalent for the answer options, deliberately. Every
    #: candidate sees them in the authored order, which AnswerOptions.position
    #: fixes for every page at once — the bank, the authoring form and the
    #: player. Shuffling per candidate would need the order recorded here as
    #: well, and it buys little: drawing 20 questions from a pool of several
    #: hundred already means two candidates share barely one question. It also
    #: breaks any option that depends on where it sits, "All of the above"
    #: being the obvious one.
    position = models.PositiveSmallIntegerField()

    #: What this question is worth on *this* paper. A snapshot, because
    #: Exam.total_marks_for() multiplies by Exam.MARKS_PER_QUESTION — if that
    #: constant ever changes, every past paper would silently re-total.
    marks = models.PositiveIntegerField()

    #: Objective answer. PROTECT so an answer can never point at an option that
    #: has been deleted, which would quietly turn a graded response into a blank.
    selected_option = models.ForeignKey(
        AnswerOptions,
        on_delete=models.PROTECT,
        related_name="chosen_on",
        blank=True,
        null=True,
    )

    #: Subjective answer. Written incrementally by autosave, not only at submit
    #: — a closed tab must not lose work, and an abandoned paper should grade on
    #: what was actually written.
    written_answer = models.TextField(blank=True)

    #: Filled by auto-grading for objective questions, by an examiner for
    #: subjective ones. Null means not yet graded, which is why it is not
    #: defaulted to 0 — unanswered and ungraded are different states.
    marks_awarded = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        db_table = "exam_sheet_questions"
        ordering = ["position"]
        constraints = [
            # Two questions cannot occupy the same slot on one paper.
            models.UniqueConstraint(
                fields=["sheet", "position"],
                name="one_question_per_sheet_position",
            ),
            # The draw is without replacement. Enforced here rather than trusted
            # to the code that shuffles, because a candidate seeing the same
            # question twice is the kind of bug nobody notices until a
            # candidate reports it.
            models.UniqueConstraint(
                fields=["sheet", "question"],
                name="no_duplicate_question_on_sheet",
            ),
        ]

    def __str__(self):
        return f"Q{self.position} of {self.sheet_id}"
