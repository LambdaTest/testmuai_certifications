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
from .models import Exam, ExamBooking, Subject, Question
import math

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


class AuthoringForm(forms.ModelForm):
    """
    Shared behaviour for the admin authoring forms.

    Two things every one of them wants:

    · **A derived slug.** Left blank, it is generated from whichever field
      `slug_source` names, made unique by appending -2, -3… A slug the author
      *typed* is left alone, so a collision is reported to them rather than
      silently renamed — they chose that value and should be told.

    · **Consistent inputs.** The design-system classes go on the widgets,
      because {{ form.name }} generates the tag and a template cannot style it.

    Subclasses set `slug_source` and otherwise just declare Meta. Written once
    here rather than copied into each form: two copies of the slug rule would
    eventually disagree about what a blank slug means.
    """

    #: Field the slug is derived from when left blank.
    slug_source = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "slug" in self.fields:
            # Optional on the form, still required on the model — clean() fills
            # it in from `slug_source`.
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
        taken = self._meta.model.objects.exclude(pk=self.instance.pk)
        candidate, suffix = base, 2
        while taken.filter(slug=candidate).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def clean(self):
        cleaned = super().clean()

        if "slug" in self.fields and not cleaned.get("slug"):
            source = cleaned.get(self.slug_source) if self.slug_source else None
            if source:
                base = slugify(source)
                if not base:
                    self.add_error(
                        "slug",
                        "A slug could not be generated from that name. "
                        "Please enter one.",
                    )
                else:
                    cleaned["slug"] = self._available_slug(base)

        return cleaned


class SubjectForm(AuthoringForm):
    """
    Authoring form for a subject.

    A ModelForm, unlike the booking forms: every input maps onto a column, so
    there is nothing for a hand-written Form to add. BookingForm is a plain
    Form only because date + hour + minute + timezone collapse into a single
    `scheduled_at`.

    `created_by` is deliberately not a field — a user must not choose who
    authored a subject. The view sets it from request.user.
    """

    slug_source = "name"

    class Meta:
        model = Subject
        fields = ["name", "slug", "description"]
        help_texts = {
            "slug": "Leave blank to generate one from the name.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Selenium"}),
            "slug": forms.TextInput(attrs={"placeholder": "selenium"}),
            "description": forms.Textarea(attrs={"rows": 4}),
        }


class ExamForm(AuthoringForm):
    """
    This is the form for handling exam creation, validation, and modification (of existing exams).
    It is a model form connecting directly to the Exam model, allowing for easy data handling and validation.
    """

    #: Which submit button was pressed — "draft" or "publish". Not a model field,
    #: because status must not be typeable; the button decides it. Declaring it
    #: anyway lets clean() see the author's intent, so publishing can be refused
    #: with a readable error rather than the view quietly downgrading it.
    #: Never rendered — the two <button name="action"> elements post it.
    action = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Exam
        # maximum_marks is deliberately absent. It is derived from the questions
        # served, so exposing it as a field would let a submitted value overwrite
        # the computed one — and a `readonly` input is no defence, since the
        # browser still posts it and devtools can change it.
        fields = ['subject', 'exam_name', 'slug', 'exam_type', 'exam_level',
                  'question_selection', 'question_count',
                  'marketing_url', 'passing_marks', 'description']
        labels = {
            'subject': 'Subject',
            'exam_name': 'Exam Name',
            'slug': 'Slug',
            'exam_type': 'Exam Type',
            'question_selection': 'Question Selection',
            'question_count': 'Questions to serve',
            'passing_marks': 'Passing Marks',
            'exam_level': 'Exam Level',
            'description': 'Exam Description'
        }
        help_texts = {
            'slug': "Leave blank to generate one from the exam name.",
            'marketing_url': "Optional. A URL that takes marketing page for this Exam."
        }
        widgets = {
            "exam_name": forms.TextInput(attrs={"placeholder": "e.g. Selenium Basics"}),
            "description": forms.Textarea(attrs={"rows": 4, "placeholder": "A brief description of the exam."}),
            "slug": forms.TextInput(attrs={"placeholder": "selenium-basics"}),
            "exam_level": forms.Select(attrs={"placeholder": "Select Exam Level"}),
            "marketing_url": forms.URLInput(attrs={"placeholder": "https://example.com/selenium-basics"}),
            "passing_marks": forms.NumberInput(attrs={"min": 1}),
            # x-model lets Alpine mirror the typed value so the derived total
            # updates as you type. Django passes unknown attrs straight through
            # to the HTML, so framework hooks can live on a ModelForm widget.
            "question_count": forms.NumberInput(attrs={
                "min": 1,
                "x-model.number": "count",
                "class": ("h-11 w-full max-w-[12rem] rounded-lg border border-zinc-300 bg-white px-3 "
                          "text-sm outline-none focus-visible:border-brand focus-visible:ring-3 "
                          "focus-visible:ring-brand/30"),
            }),
            "subject": forms.Select(attrs={"placeholder": "Select Subject"}),
            "exam_type": forms.Select(attrs={"placeholder": "Select Exam Type"}),
        }

    slug_source = "exam_name"

    def clean(self):
        """
        Two rules the browser cannot be trusted with.

        The template already warns about both, but a warning is decoration: the
        form can be posted with JavaScript off, from curl, or from a devtools
        edit. Anything that must be true of the stored row is checked here.
        """
        cleaned = super().clean()  # AuthoringForm fills in a blank slug

        selection = cleaned.get("question_selection")
        count = cleaned.get("question_count")

        if selection == Exam.QuestionSelection.RANDOM:
            if not count:
                self.add_error("question_count", "Say how many questions to serve.")
        elif selection == Exam.QuestionSelection.MANUAL:
            # A manual paper's questions are picked, not counted. Clearing this
            # stops a leftover number from an earlier edit reading as meaningful.
            cleaned["question_count"] = count = None

        # Same helper the model saves through, so the number validated here is
        # exactly the number that lands in the column.
        maximum = Exam.total_marks_for(selection, count)
        if maximum is None:
            # Manual: nothing to derive from yet, so fall back to whatever the
            # exam already carried. On a new manual exam that is None and the
            # check below simply doesn't apply.
            maximum = self.instance.maximum_marks

        # Left blank, the pass mark defaults to a share of the paper. Written
        # back into cleaned_data, not just a local — save() reads cleaned_data,
        # so a value only rebound to a variable never reaches the column.
        #
        # `not passing` rather than `== ""`: an IntegerField cleans a blank input
        # to None, never to an empty string, so testing for "" would only ever
        # catch a literal typed 0 and let the actual blank case through.
        #
        # Guarded on `maximum` because it is None for a manual paper — there is
        # nothing to take a share of, and multiplying None raises.
        passing = cleaned.get("passing_marks")
        if not passing and maximum:
            # ceil, so a 25-mark paper needs 18 rather than 17.5.
            passing = cleaned["passing_marks"] = math.ceil(
                maximum * Exam.DEFAULT_PASS_RATIO
            )

        if passing and maximum and passing > maximum:
            self.add_error(
                "passing_marks",
                f"Cannot be more than the maximum of {maximum} marks.",
            )

        # The template greys out the Publish button for a manual exam. That stops
        # the click, not the request — so the rule is enforced here too, where it
        # actually holds.
        if (
            cleaned.get("action") == "publish"
            and selection == Exam.QuestionSelection.MANUAL
        ):
            self.add_error(
                None,
                "Choosing questions by hand isn't built yet, so a manual exam "
                "can only be saved as a draft.",
            )

        return cleaned


class QuestionForm(AuthoringForm):
    """
    This is the form for handling question creation and validation.
    It is a model form connecting directly to the Question model, allowing for easy data handling and validation.
    """

    slug_source = "question_text"

    class Meta:
        model = Question
        fields = ['question_text', 'associated_image','associated_audio', 'associated_video', 'question_tags', 'marks', 'status',
                  'question_type', 'question_difficulty', 'question_subject', ]
        labels = {
            'question_text': 'Question Text',
            'associated_image': 'Associated Image',
            'associated_audio': 'Associated Audio',
            'associated_video': 'Associated Video',
            'question_tags': 'Question Tags',
            'marks': 'Marks',
            'status': 'Status',
            'question_type': 'Question Type',
            'question_difficulty': 'Question Difficulty',
            'question_subject': 'Question Subject',
        }
        help_texts = {
            'question_tags': "Comma-separated tags for categorizing the question.",
            'marks': "The number of marks allocated for this question. Default: 5",
            'status': "Select whether the question is active or retired."
        }
        widgets = {
            "question_text": forms.Textarea(attrs={"rows": 4, "placeholder": "Enter the question text here."}),
            "associated_image": forms.ClearableFileInput(attrs={"accept": ".jpg,.jpeg,.png,.gif, webp"}),
            "associated_audio": forms.ClearableFileInput(attrs={"accept": ".mp3,.wav,.m4a,.ogg"}),
            "associated_video": forms.ClearableFileInput(attrs={"accept": ".mp4,.avi,.mov"}),
            "question_tags": forms.TextInput(attrs={"placeholder": "e.g. math, algebra, geometry"}),
            "question_type": forms.Select(),
            "question_difficulty": forms.Select(),
            "question_subject": forms.Select(),
        }

    def clean(self):
            """
            Validation for the QuestionForm to ensure that the data entered is valid and meets the requirements of the Question model.
            """
            cleaned = super().clean()  # AuthoringForm fills in a blank slug
            associated_audio = cleaned.get("associated_audio")
            associated_video = cleaned.get("associated_video")
            associated_image = cleaned.get("associated_image")
            file = []
            media = []
            if associated_audio:
                media.append("audio")
                file.append(associated_audio)
            if associated_video:
                media.append("video")
                file.append(associated_video)
            if associated_image:
                media.append("image")
                file.append(associated_image)
            if len(media) > 1:
                if not self.is_valid(file, media):
                    raise forms.ValidationError(
                        f"Media validation failed. Please upload correct type and within correct size limits."
                    )
            tag = cleaned.get("question_tags")
            if tag:
                for t in tag.split(","):
                    t = t.lower()


    def is_valid(self, file, media):
        """
        Validates the uploaded media files based on their type and size.
        Returns True if all files are valid, False otherwise.
        """
        for f, m in zip(file, media):
            if m == "audio":
                if f.size > 5 * 1024 * 1024 and f.split(".")[-1].lower() not in ["mp3", "wav", "m4a", "ogg"]:  # 5 MB limit for audio
                    return False
            elif m == "video":
                if f.size > 50 * 1024 * 1024 and f.split(".")[-1].lower() not in ["mp4", "avi", "mov"]:  # 50 MB limit for video
                    return False
            elif m == "image":
                if f.size > 5 * 1024 * 1024 and f.split(".")[-1].lower() not in ["jpg", "jpeg", "png", "gif", "webp"]:  # 5 MB limit for image
                    return False
        return True

