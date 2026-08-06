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

from django.conf import settings
from django.db import models


class Certification(models.Model):
    """
    The product a candidate earns. This app is the source of truth — the main
    TestMu AI site holds only marketing pages on top.

    Exam versions, sections and the question bank come later; this is the
    minimum the booking page needs.
    """

    class Level(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        ADVANCED = "advanced", "Advanced"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    name = models.CharField(max_length=255)

    #: Mirrors the slug the main site already uses in its catalog URLs
    #: (testmuai.com/certifications/<slug>/). Internal, but keeping them aligned
    #: gives both systems one vocabulary.
    slug = models.SlugField(max_length=255, unique=True)

    level = models.CharField(max_length=16, choices=Level.choices)
    description = models.TextField(blank=True)
    icon_url = models.URLField(blank=True)
    marketing_url = models.URLField(blank=True)

    #: TestMu AI's own numeric course id, as passed by the current redirect
    #: (?id=2934). Nullable and unused for now — it exists so a prefill hint can
    #: be mapped later without a migration.
    external_ref = models.CharField(max_length=64, blank=True, null=True, db_index=True)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "certifications"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_bookable(self) -> bool:
        # Once exam versions exist this also requires a published version.
        return self.status == self.Status.PUBLISHED


class Booking(models.Model):
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

    certification = models.ForeignKey(
        Certification, on_delete=models.PROTECT, related_name="bookings"
    )

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
            # One open booking per certification per candidate. Partial, so a
            # cancelled booking doesn't block rebooking.
            models.UniqueConstraint(
                fields=["candidate", "certification"],
                condition=models.Q(status="booked"),
                name="one_open_booking_per_certification",
            ),
        ]

    def __str__(self):
        return f"{self.certification} @ {self.scheduled_at:%Y-%m-%d %H:%M} UTC"

    @property
    def local_scheduled_at(self):
        from .timezones import to_local

        return to_local(self.scheduled_at, self.booked_timezone)
