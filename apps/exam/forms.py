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
from django.utils.text import slugify

from . import timezones
from .models import Exam, ExamBooking, Subject


def occupied_minutes(exam):
    """
    How long an exam actually ties a candidate up, for clash checking.

    An objective exam is a real sitting, so the full duration is occupied. A
    subjective exam is a 36-hour *window with a deadline*, not 36 hours at a
    desk — blocking all of it would make a day and a half unbookable. It
    therefore occupies no span, leaving BOOKING_GAP_MINUTES either side of its
    start.

    Same reasoning as CALENDAR_BLOCK_MAX_MINUTES in calendar.py, which caps the
    calendar entry for exactly this case.
    """
    if exam.exam_type == Exam.Type.OBJECTIVE:
        return exam.duration_minutes
    return 0


class ScheduleForm(forms.Form):
    """Picks a moment in time and validates it against the booking window."""

    date = forms.DateField()
    hour = forms.IntegerField(min_value=0, max_value=23)
    minute = forms.IntegerField(min_value=0, max_value=59)
    timezone = forms.CharField(max_length=64)

    def __init__(self, *args, candidate=None, exclude_booking=None, **kwargs):
        # Clash detection needs to know whose bookings to look at. With no
        # candidate — every booking made through /book until OIDC lands — the
        # check is skipped, because "this candidate's other bookings" has no
        # meaning when they are all anonymous.
        self.candidate = candidate
        self.exclude_booking = exclude_booking
        super().__init__(*args, **kwargs)

    def new_exam(self):
        """The exam being scheduled. Subclasses supply it."""
        raise NotImplementedError

    def _check_clash(self, scheduled_at):
        """
        Rejects a slot that leaves less than BOOKING_GAP_MINUTES clear either
        side of an exam this candidate has already booked.

        Two exams clash when neither finishes far enough ahead of the other
        starting:

            new_start   <  existing_end + gap   AND
            other_start <  new_end      + gap

        Done in Python rather than SQL because each booking's end depends on
        its own exam's duration, and a candidate has only a handful of open
        bookings — so the query stays trivial.
        """
        if self.candidate is None or self.candidate.pk is None:
            return

        gap = timedelta(minutes=settings.BOOKING_GAP_MINUTES)
        new_end = scheduled_at + timedelta(minutes=occupied_minutes(self.new_exam()))

        others = ExamBooking.objects.filter(
            candidate=self.candidate, status=ExamBooking.Status.BOOKED
        ).select_related("exam")
        if self.exclude_booking is not None:
            # Rescheduling: a booking must not clash with itself.
            others = others.exclude(pk=self.exclude_booking.pk)

        for other in others:
            other_end = other.scheduled_at + timedelta(
                minutes=occupied_minutes(other.exam)
            )
            if scheduled_at < other_end + gap and other.scheduled_at < new_end + gap:
                local = timezones.to_local(other.scheduled_at, other.booked_timezone)
                raise forms.ValidationError(
                    f"This clashes with {other.exam.exam_name} on "
                    f"{local:%a, %d %b %Y at %H:%M} ({other.booked_timezone}). "
                    f"Leave at least {settings.BOOKING_GAP_MINUTES} minutes "
                    f"between exams."
                )

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

        self._check_clash(scheduled_at)

        cleaned["scheduled_at"] = scheduled_at
        return cleaned


class BookingForm(ScheduleForm):
    exam = forms.ModelChoiceField(
        queryset=Exam.objects.filter(status=Exam.Status.PUBLISHED),
        to_field_name="slug",
    )

    def new_exam(self):
        return self.cleaned_data["exam"]

    def save(self, candidate=None) -> ExamBooking:
        return ExamBooking.objects.create(
            candidate=candidate,
            exam=self.cleaned_data["exam"],
            scheduled_at=self.cleaned_data["scheduled_at"],
            booked_timezone=self.cleaned_data["timezone"],
        )


class RescheduleForm(ScheduleForm):
    """Moves an existing booking. The exam never changes — only the slot."""

    def __init__(self, *args, booking=None, **kwargs):
        self.booking = booking
        kwargs.setdefault("exclude_booking", booking)
        super().__init__(*args, **kwargs)

    def new_exam(self):
        return self.booking.exam

    def apply(self, booking: ExamBooking) -> ExamBooking:
        booking.scheduled_at = self.cleaned_data["scheduled_at"]
        booking.booked_timezone = self.cleaned_data["timezone"]
        booking.save(update_fields=["scheduled_at", "booked_timezone", "updated_at"])
        return booking


class SubjectForm(forms.ModelForm):
    """
    Authoring form for a subject.

    A ModelForm, unlike the booking forms: every input maps onto a column, so
    there is nothing for a hand-written Form to add. BookingForm is a plain
    Form only because date + hour + minute + timezone collapse into a single
    `scheduled_at`.

    `created_by` is deliberately not a field — a user must not choose who
    authored a subject. The view sets it from request.user.
    """

    class Meta:
        model = Subject
        fields = ["name", "slug", "description", "subject_level"]
        labels = {"subject_level": "Level"}
        help_texts = {
            "slug": "Leave blank to generate one from the name.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Selenium"}),
            "slug": forms.TextInput(attrs={"placeholder": "selenium"}),
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Optional on the form, still required on the model — clean() fills it
        # in from the name when left blank.
        self.fields["slug"].required = False

        css = (
            "w-full rounded-lg border border-zinc-300 bg-white px-3 py-2.5 text-sm "
            "outline-none focus-visible:border-brand focus-visible:ring-3 "
            "focus-visible:ring-brand/30"
        )
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", css)

    def _available_slug(self, base):
        """`selenium`, else `selenium-2`, `selenium-3`… — first one free."""
        taken = Subject.objects.exclude(pk=self.instance.pk)
        candidate, suffix = base, 2
        while taken.filter(slug=candidate).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def clean(self):
        cleaned = super().clean()

        # A typed slug is left alone: if it collides, the model's unique check
        # reports it, because the author chose that value and should be told.
        # A derived one is made unique silently — they didn't choose it, so a
        # collision is not their problem.
        if not cleaned.get("slug") and cleaned.get("name"):
            base = slugify(cleaned["name"])
            if not base:
                self.add_error(
                    "slug",
                    "A slug could not be generated from that name. Please enter one.",
                )
            else:
                cleaned["slug"] = self._available_slug(base)

        return cleaned
