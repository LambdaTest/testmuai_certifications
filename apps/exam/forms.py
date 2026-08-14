"""
Booking and rescheduling forms.

The scheduling rules live here, not only in the UI. The date picker disables
past days and caps the horizon, but a form post can be made directly — so the
same rules are enforced server-side.

Booking and rescheduling share those rules through ``ScheduleForm``. Two copies
would drift, and a drifted rule means one route accepts a slot the other
rejects.
"""

from datetime import timedelta

from django import forms
from django.conf import settings
from django.utils import timezone as dj_timezone

from . import timezones
from .models import Exam, ExamBooking


class ScheduleForm(forms.Form):
    """Picks a moment in time and validates it against the booking window."""

    date = forms.DateField()
    hour = forms.IntegerField(min_value=0, max_value=23)
    minute = forms.IntegerField(min_value=0, max_value=59)
    timezone = forms.CharField(max_length=64)

    def clean_timezone(self):
        name = timezones.canonical(self.cleaned_data["timezone"])
        if not timezones.is_valid(name):
            raise forms.ValidationError("Unknown timezone.")
        return name

    def clean(self):
        cleaned = super().clean()
        day = cleaned.get("date")
        hour = cleaned.get("hour")
        minute = cleaned.get("minute")
        tz = cleaned.get("timezone")

        if day is None or hour is None or minute is None or not tz:
            return cleaned

        scheduled_at = timezones.compose_utc(day, hour, minute, tz)
        now = dj_timezone.now()

        earliest = now + timedelta(days=settings.BOOKING_MIN_DAYS_AHEAD)
        if scheduled_at < earliest:
            raise forms.ValidationError(
                f"Bookings must be at least "
                f"{settings.BOOKING_MIN_DAYS_AHEAD} day(s) ahead."
            )

        latest = now + timedelta(days=settings.BOOKING_MAX_MONTHS_AHEAD * 31)
        if scheduled_at > latest:
            raise forms.ValidationError(
                f"Bookings cannot be more than "
                f"{settings.BOOKING_MAX_MONTHS_AHEAD} months ahead."
            )

        cleaned["scheduled_at"] = scheduled_at
        return cleaned


class BookingForm(ScheduleForm):
    exam = forms.ModelChoiceField(
        queryset=Exam.objects.filter(status=Exam.Status.PUBLISHED),
        to_field_name="slug",
    )

    def save(self, candidate=None) -> ExamBooking:
        return ExamBooking.objects.create(
            candidate=candidate,
            exam=self.cleaned_data["exam"],
            scheduled_at=self.cleaned_data["scheduled_at"],
            booked_timezone=self.cleaned_data["timezone"],
        )


class RescheduleForm(ScheduleForm):
    """Moves an existing booking. The exam never changes — only the slot."""

    def apply(self, booking: ExamBooking) -> ExamBooking:
        booking.scheduled_at = self.cleaned_data["scheduled_at"]
        booking.booked_timezone = self.cleaned_data["timezone"]
        booking.save(update_fields=["scheduled_at", "booked_timezone", "updated_at"])
        return booking
