"""
Booking form.

The scheduling rules live here, not only in the UI. The date picker disables
past days and caps the horizon, but a form post can be made directly — so the
same rules are enforced server-side.
"""

from datetime import timedelta

from django import forms
from django.conf import settings
from django.utils import timezone as dj_timezone

from . import timezones
from .models import Booking, Exam


class BookingForm(forms.Form):
    exam = forms.ModelChoiceField(
        queryset=Exam.objects.filter(status=Exam.Status.PUBLISHED),
        to_field_name="slug",
    )
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

    def save(self, candidate=None) -> Booking:
        return Booking.objects.create(
            candidate=candidate,
            exam=self.cleaned_data["exam"],
            scheduled_at=self.cleaned_data["scheduled_at"],
            booked_timezone=self.cleaned_data["timezone"],
        )
