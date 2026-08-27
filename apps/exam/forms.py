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
from django.core.validators import FileExtensionValidator
from django.forms import inlineformset_factory
from django.forms.models import BaseInlineFormSet
from django.utils import timezone as dj_timezone
from django.utils.text import slugify

from . import timezones
from .models import AnswerOptions, Audio, Exam, ExamBooking, Image, Question, Subject, Video
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

# --- Question authoring ------------------------------------------------------
#
# One place each media rule is written. These feed the form fields, and the view
# passes them to the template so the byline under each input states the number
# actually enforced — a "under 5 MB" typed into the markup drifts the day the
# limit changes.
#
# Video gets a larger ceiling than the other two because a screen recording of
# any useful length runs to tens of megabytes; a limit an author cannot work
# within just means they stop attaching video.
MAX_IMAGE_MB = 5
MAX_AUDIO_MB = 5
MAX_VIDEO_MB = 50

IMAGE_EXTENSIONS = ["png", "jpg", "jpeg", "gif", "webp"]
AUDIO_EXTENSIONS = ["mp3", "m4a", "wav", "ogg"]
#: MP4 and WebM only — what a browser can actually play. MOV, AVI and MKV upload
#: happily and then fail silently in <video>, which a candidate discovers
#: mid-exam. SVG is likewise absent from the image list: it is XML, it can carry
#: a <script>, and MEDIA_URL is same-origin.
VIDEO_EXTENSIONS = ["mp4", "webm"]


def max_size(megabytes):
    """
    Builds a validator that rejects an upload larger than `megabytes`.

    Size cannot be checked in the browser in any way that counts: `accept`
    filters the file picker and nothing else, and Django applies no ceiling of
    its own — FILE_UPLOAD_MAX_MEMORY_SIZE only chooses between memory and a
    temp file, and DATA_UPLOAD_MAX_MEMORY_SIZE explicitly excludes file data.
    This is the only place the limit is real.

    A closure is fine here because the validator is attached to a *form* field.
    Model-field validators are serialized into migrations by import path, which
    is why a closure cannot be used there — a form is never serialized.
    """
    limit = megabytes * 1024 * 1024

    def validate(upload):
        if upload.size > limit:
            raise forms.ValidationError(
                f"That file is {upload.size / 1024 / 1024:.1f} MB. "
                f"The limit is {megabytes} MB."
            )

    return validate


def _upload_field(label, extensions, megabytes):
    """One of the three media inputs: an upload, validated on both counts."""
    return forms.FileField(
        required=False,
        label=label,
        validators=[FileExtensionValidator(extensions), max_size(megabytes)],
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ",".join(f".{e}" for e in extensions),
                "class": (
                    "w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 "
                    "text-[13px] file:mr-3 file:rounded file:border-0 file:bg-surface "
                    "file:px-2.5 file:py-1 file:text-[12.5px] file:font-semibold"
                ),
            }
        ),
    )


class MediaUploadMixin:
    """
    Shared by any form whose model points at Image / Audio / Video by FK but
    whose *input* is a file.

    Subclasses declare MEDIA_UPLOADS as a tuple of
    ``(form field, media model, file column, FK on the instance)`` and set
    ``self.user`` before save. Written once rather than copied into both forms:
    two copies of "create the row, then attach it" would eventually disagree
    about which of those steps is allowed to fail.
    """

    #: (upload field, media model, its file column, FK on this form's model)
    MEDIA_UPLOADS = ()

    def attach_media(self, obj):
        """Turns each upload into a row of its own model and points `obj` at it."""
        for field, model, column, fk in self.MEDIA_UPLOADS:
            upload = self.cleaned_data.get(field)
            if not upload:
                continue
            media = model.objects.create(**{column: upload, "created_by": self.user})
            setattr(obj, fk, media)


class QuestionForm(MediaUploadMixin, AuthoringForm):
    """
    Authoring form for one question.

    Subclasses AuthoringForm only for its widget styling. A question has no
    slug, and that class guards its slug work on ``"slug" in self.fields``, so
    none of it fires — there is deliberately no `slug_source` here.

    **Media is uploaded, not chosen.** ``associated_image`` and its two
    siblings are ForeignKeys, so listing them in Meta.fields makes a ModelForm
    generate ModelChoiceFields — dropdowns of existing rows that expect a
    primary key. Pointing a ClearableFileInput at one changes how it draws and
    nothing else: the field still wants a pk, so an uploaded file either
    vanishes (no request.FILES) or fails with "Select a valid choice".

    So the three FKs stay out of Meta.fields, and three upload fields take
    their place under *different names*. The names matter. A declared field
    called ``associated_image`` would win the collision — declared fields beat
    generated ones — but ``_post_clean`` would then hand an UploadedFile to
    ``instance.associated_image``, which wants an Image. A separate name keeps
    the upload out of ``construct_instance``'s reach entirely, and ``save()``
    builds the row and attaches it.

    **The extension validators are re-declared here on purpose.** They already
    exist on Image.image_file and friends, but ``Model.save()`` does not call
    ``full_clean()`` — so ``Image.objects.create(...)`` runs no validation at
    all. A model-field validator only fires when a ModelForm validates that
    model. This form creates those rows itself, so the check has to live here.

    Requires `user`: Question.created_by is non-nullable, and so is created_by
    on each of the three media models.
    """

    image_upload = _upload_field("Image", IMAGE_EXTENSIONS, MAX_IMAGE_MB)
    audio_upload = _upload_field("Audio", AUDIO_EXTENSIONS, MAX_AUDIO_MB)
    video_upload = _upload_field("Video", VIDEO_EXTENSIONS, MAX_VIDEO_MB)

    MEDIA_UPLOADS = (
        ("image_upload", Image, "image_file", "associated_image"),
        ("audio_upload", Audio, "audio_file", "associated_audio"),
        ("video_upload", Video, "video_file", "associated_video"),
    )

    class Meta:
        model = Question
        # `status` is absent deliberately: a question is ACTIVE the moment it is
        # written, and retiring one is an action on the bank listing, not a
        # dropdown an author picks from while writing. `created_by` likewise —
        # nobody chooses who authored a question.
        fields = [
            "question_text",
            "question_subject",
            "question_type",
            "question_difficulty",
            "marks",
            "question_tags",
        ]
        labels = {
            "question_text": "Question",
            "question_subject": "Subject",
            "question_type": "Type",
            "question_difficulty": "Difficulty",
            "question_tags": "Tags",
        }
        help_texts = {
            "question_tags": (
                "Optional. Comma-separated — subject and difficulty are the real "
                "filters, so use these only for what neither captures."
            ),
        }
        widgets = {
            "question_text": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "What does an explicit wait do in Selenium?",
                }
            ),
            # x-model so the page reshapes as the type changes — objective
            # questions take answer options and a fixed mark, subjective ones
            # take neither. Django passes unknown widget attrs straight to the
            # HTML, so framework hooks can live on a ModelForm widget.
            "question_type": forms.Select(attrs={"x-model": "type"}),
            "marks": forms.NumberInput(attrs={"min": 1}),
            # A TextField renders as a Textarea by default. Tags are one line.
            "question_tags": forms.TextInput(
                attrs={"placeholder": "waits, locators, grid"}
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["question_subject"].empty_label = "Select subject"

    def clean_question_tags(self):
        """
        Normalises the tag list rather than rejecting it.

        The help text calls for comma-separated lowercase; nothing made that
        true, so "Waits, Locators" and "waits,locators" were different strings
        and any future tag filter would silently miss half the bank. A
        clean_<field> method may transform: whatever it returns replaces the
        value in cleaned_data, which is what save() reads.
        """
        tags = self.cleaned_data.get("question_tags", "")
        parts = [part.strip().lower() for part in tags.split(",")]
        return ", ".join(part for part in parts if part)

    def clean(self):
        cleaned = super().clean()

        marks = cleaned.get("marks")

        if cleaned.get("question_type") == Question.Type.OBJECTIVE:
            # Overwritten rather than validated. The template shows objective
            # marks as a fixed 5 and posts a hidden input to match, so there is
            # nothing an author can get wrong and an error message would only
            # confuse — but a hand-made post can send any number, and
            # Exam.total_marks_for() *multiplies* count by MARKS_PER_QUESTION
            # rather than summing real questions. One question worth 7 and
            # every randomised paper's maximum_marks is a lie.
            cleaned["marks"] = Exam.MARKS_PER_QUESTION
        elif marks is not None and marks < 1:
            # PositiveIntegerField permits 0, so this is the one marks case a
            # subjective author really can get wrong.
            self.add_error("marks", "A question must be worth at least one mark.")

        return cleaned

    def save(self, commit=True):
        question = super().save(commit=False)
        question.created_by = self.user

        # Media rows are written whether or not `commit` is set, because a
        # caller using commit=False still needs the FKs on the instance before
        # it saves — that is exactly what the add_question view does. The cost
        # is an orphan Image row if a caller then discards the question, which
        # no caller does after is_valid().
        self.attach_media(question)

        if commit:
            question.save()
        return question


class BaseAnswerOptionFormSet(BaseInlineFormSet):
    """
    The rule a single AnswerOptions row cannot express: an objective question
    needs at least two options, and exactly one of them marked correct.

    It lives on the formset because it spans rows. It cannot be a field
    validator — one option knows nothing about its siblings — and it cannot be
    a database constraint, for the same reason: Postgres checks a row against
    itself, not against a set.

    A formset has its own clean() sitting above the individual forms, run once
    they have all validated. `any(self.errors)` bails early because a child in
    error has an incomplete cleaned_data, and counting correct answers across
    half-cleaned forms reports a confusing second error on top of the real one.

    Raising here produces a *non-form* error — the template renders it through
    formset.non_form_errors, not through any single field.
    """

    def clean(self):
        super().clean()

        if any(self.errors):
            return

        # self.instance is the Question this formset hangs off — the same object
        # QuestionForm populated in its _post_clean. So the type checked here is
        # the one just submitted, not whatever the model defaults to.
        filled = [f for f in self.forms if f.cleaned_data.get("answer_option_text")]

        if self.instance.question_type != Question.Type.OBJECTIVE:
            if filled:
                raise forms.ValidationError(
                    "A subjective question is marked by an examiner, so it "
                    "cannot carry answer options. Clear them or switch the "
                    "type back to objective."
                )
            return

        if len(filled) < 2:
            raise forms.ValidationError(
                "An objective question needs at least two answer options."
            )

        correct = [f for f in filled if f.cleaned_data.get("is_correct")]
        if len(correct) != 1:
            raise forms.ValidationError("Mark exactly one option as correct.")


#: Six slots, of which the template shows four and reveals the rest on demand.
#:
#: Rendering them up front rather than cloning markup in JavaScript is
#: deliberate: adding a form client-side means incrementing TOTAL_FORMS in the
#: management form by hand, and a formset whose management form disagrees with
#: the posted data raises rather than validates. Empty slots cost nothing — a
#: form left untouched has not changed, so Django skips it instead of saving a
#: blank row.
#:
#: `is_correct` is a checkbox per row, because that is what the column actually
#: is. The template makes the group behave like radio buttons; the formset's
#: clean() is what enforces "exactly one", since a hand-made post can tick all
#: six.
AnswerOptionFormSet = inlineformset_factory(
    Question,
    AnswerOptions,
    formset=BaseAnswerOptionFormSet,
    fields=["answer_option_text", "is_correct"],
    extra=6,
    # Nothing to delete on an add page. Editing a question will want this, and
    # turning it on means rendering the DELETE checkbox the factory then adds.
    can_delete=False,
    widgets={
        "answer_option_text": forms.TextInput(
            attrs={
                "class": (
                    "h-11 w-full rounded-lg border bg-white px-3 text-sm outline-none "
                    "focus-visible:ring-3 focus-visible:ring-brand/30"
                )
            }
        ),
    },
)
