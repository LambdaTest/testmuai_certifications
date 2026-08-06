"""
Bookings.

Self-scheduled, not slot-based: candidates pick their own date and time. There
are no pre-defined slots, no capacity, and therefore no seat contention — the
concurrency problem that would otherwise dominate this module does not exist.
"""

from django.conf import settings
from django.db import models


class Booking(models.Model):
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
        "certifications.Certification",
        on_delete=models.PROTECT,
        related_name="bookings",
    )

    #: Stored UTC. Always.
    scheduled_at = models.DateTimeField()

    #: The IANA zone the candidate booked in. Kept alongside the instant
    #: because it is what reminders display, and what you reason about if
    #: someone disputes the time.
    booked_timezone = models.CharField(max_length=64)

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.BOOKED
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bookings"
        ordering = ["-scheduled_at"]
        constraints = [
            # One open booking per certification per candidate. A partial
            # constraint so cancelled bookings don't block rebooking.
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
