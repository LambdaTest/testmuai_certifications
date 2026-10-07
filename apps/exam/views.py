"""
The booking page.

/book is the entry point into this app from the main TestMu AI site. It takes no
path parameter: the candidate chooses the certification from a selector, then
picks their own date and time.
"""

import json
import secrets
from dataclasses import asdict

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse, request
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import imports
from . import timezones
from .calendar import build_ics
from . import forms as exam_forms
from .forms import (
    AnswerOptionFormSet,
    BookingForm,
    ExamForm,
    QuestionForm,
    RescheduleForm,
    SaveAnswerForm,
    SubjectForm,
    ImportQuestionsForm,
    ExamSheetFormSubjective,
)
from .models import (Exam, ExamBooking, ExamSheet, ExamSheetQuestion,
                     Subject, SubjectiveSubmission, Question, Audio, Video)
from apps.home.models import User
from apps.home.decorators import role_required
from datetime import timedelta

from django.utils import timezone
from django.db import transaction
from django.db.models import Case, When, IntegerField


def _exam_payload():
    """Bookable certifications, as the client-side picker needs them."""
    return [
        {
            "slug": c.slug,
            "name": c.exam_name,
            "level": c.get_exam_level_display(),
            "description": c.description,
        }
        for c in Exam.objects.filter(status=Exam.Status.PUBLISHED)
]


def book(request):
    # Optional prefill hint from the main site. Its redirect carries TestMu AI's
    # own numeric course id (?id=2934); ?exam=<slug> is also accepted. A missing,
    # unknown or stale value falls back silently to "Choose an exam" — never an
    # error. Nothing depends on this working.
    hint = request.GET.get("exam") or request.GET.get("id")
    preselected = ""
    if hint:
        published = Exam.objects.filter(status=Exam.Status.PUBLISHED)
        match = (
            published.filter(slug=hint).first()
            or published.filter(external_ref=hint).first()
        )
        if match:
            preselected = match.slug

    # Anonymous only if nobody is signed in. Until the OIDC integration lands
    # that means the Django admin login, which is real enough for both of the
    # rules that depend on knowing who this is.
    candidate = request.user if request.user.is_authenticated else None
    form = BookingForm(request.POST or None, candidate=candidate)

    if request.method == "POST" and form.is_valid():
        # Passed through, not dropped. This used to save candidate=None from a
        # time when nothing was signed in, which left every booking anonymous —
        # and silently disabled the two rules that key on the candidate:
        #
        #   · one_open_booking_per_exam is a partial unique index on
        #     (candidate, exam). Two NULLs are never equal in Postgres, so it
        #     matched nothing and a candidate could hold any number of open
        #     bookings for the same exam.
        #   · the clash check in ScheduleForm returns early with no candidate,
        #     so overlapping bookings were never detected.
        #
        # Both come alive now, which is the point — but it means a booking that
        # would have been accepted yesterday can be rejected today.
        booking = form.save(candidate=candidate)
        # Redirect after POST. Reloading then re-issues a harmless GET instead
        # of re-submitting the form and creating a second booking.
        return redirect(f"{reverse('exam:book')}?booked={booking.booking_id}")

    # The booking just made, read back from the redirect so the confirmation
    # survives a reload. An unknown or malformed id simply shows nothing.
    booked = None
    if request.GET.get("booked"):
        try:
            booked = (
                ExamBooking.objects.select_related("exam")
                .filter(booking_id=request.GET["booked"])
                .first()
            )
        except (ValueError, ValidationError):
            booked = None

    exams = _exam_payload()
    tz_options = timezones.timezone_options(timezones.DEFAULT_TIMEZONE)

    context = {
        "exams_json": json.dumps(exams),
        "timezone_options_json": json.dumps(tz_options),
        "default_timezone": timezones.DEFAULT_TIMEZONE,
        "preselected": preselected,
        "min_days_ahead": settings.BOOKING_MIN_DAYS_AHEAD,
        "max_months_ahead": settings.BOOKING_MAX_MONTHS_AHEAD,
        "form": form,
        "booked": booked,
    }
    return render(request, "exam/book.html", context)


@login_required
def booking_ics(request, booking_id):
    """
    Downloads the calendar invite for one booking.

    The ownership check lives inside the lookup rather than after it, so
    another candidate's UUID returns 404 rather than 403 — we don't confirm a
    booking exists to someone who has no business knowing.
    """
    booking = get_object_or_404(
        ExamBooking.objects.select_related("exam__subject"),
        booking_id=booking_id,
        candidate=request.user,
    )
    body = build_ics(booking, url=request.build_absolute_uri(reverse("home:dashboard")))

    response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
    # Without this the browser renders the text instead of saving a file.
    response["Content-Disposition"] = f'attachment; filename="exam-{booking.booking_id}.ics"'
    return response

@login_required
def reschedule(request, booking_id):
    """
    Moves an existing booking to a new slot.
    Same ownership pattern as the .ics download: the candidate filter is part
    of the lookup, so someone else's UUID is a 404 rather than a 403. Only an
    open booking can be moved — a cancelled or attended one is not reschedulable.
    """
    booking = get_object_or_404(
        ExamBooking.objects.select_related("exam__subject"),
        booking_id=booking_id,
        candidate=request.user,
        status=ExamBooking.Status.BOOKED,
    )

    form = RescheduleForm(
        request.POST or None, booking=booking, candidate=request.user
    )
    if request.method == "POST" and form.is_valid():
        form.apply(booking)
        return redirect("home:dashboard")

    exam = booking.exam
    return render(
        request,
        "exam/reschedule.html",
        {
            "booking": booking,
            # The picker is the same component /book uses, which expects a list
            # of exams. Here the exam is fixed, so it gets a list of one.
            "exam_json": json.dumps(
                [
                    {
                        "slug": exam.slug,
                        "name": exam.exam_name,
                        "level": exam.get_exam_level_display(),
                        "description": exam.description,
                    }
                ]
            ),
            "timezone_options_json": json.dumps(
                timezones.timezone_options(booking.booked_timezone)
            ),
            # Open in the zone they booked in, not the browser's.
            "default_timezone": booking.booked_timezone,
            "min_days_ahead": settings.BOOKING_MIN_DAYS_AHEAD,
            "max_months_ahead": settings.BOOKING_MAX_MONTHS_AHEAD,
            "form": form,
        },
    )

@login_required
def my_assessments(request, status):
    """
    Shows the candidate's bookings, filtered by status.
    """
    bookings = (
        ExamBooking.objects.filter(candidate=request.user, status=status)
        .select_related("exam__subject")
        .order_by("-scheduled_at")
    )

    return render(
        request,
        "exam/my_assessments.html",
        {
            "bookings": bookings,
            "status": status,
            "status_display": ExamBooking.Status(status).label,
        },
    )

@login_required
def explore_assessment(request, booking_id):
    """
    Shows the candidate's booking details for one assessment.
    """
    booking = get_object_or_404(
        ExamBooking.objects.select_related("exam__subject"),
        booking_id=booking_id,
        candidate=request.user,
    )

    return render(
        request,
        "exam/explore_assessment.html",
        {
            "booking": booking,
        },
    )

@login_required
def cancel_booking_page(request, booking_id):
    """
    Takes the candidate to the cancel booking page.
    Shows the candidate's booking details for one assessment from where he can cancel.
    """
    booking = get_object_or_404(
        ExamBooking.objects.select_related("exam__subject"),
        booking_id=booking_id,
        candidate=request.user,
    )

    return render(
        request,
        "exam/cancel_booking.html",
        {
            "booking": booking,
        },
    )

@login_required
def cancel_booking(request, booking_id):
    """
    Cancels a candidate's booking.
    """
    booking = get_object_or_404(
        ExamBooking.objects.select_related("exam__subject"),
        booking_id=booking_id,
        candidate=request.user,
        status=ExamBooking.Status.BOOKED,
    )

    if request.method == "POST":
        booking.status = ExamBooking.Status.CANCELLED
        booking.save()
        return redirect("home:dashboard")

    return redirect("home:dashboard")

def assign_grading(request):
    """
    Assigns ungraded subjective attempts to examiners or other admins.
    """
    # Only allow superusers to access this view
    if not request.user.role != User.Role.ADMIN:
        return redirect("home:dashboard")

    # Get all ungraded subjective attempts
    ungraded_attempts = ExamBooking.objects.filter(
        status=ExamBooking.Status.ATTENDED,
        exam__subject__is_subjective=True,
        grade__isnull=True,
    ).select_related("exam", "candidate")

    # Assign each ungraded attempt to an examiner/ admin
    for attempt in ungraded_attempts:
        # Here you can implement your logic to assign the attempt to an examiner/ admin
        # For example, you can assign it to the first available superuser
        examiner = User.objects.filter(is_superuser=True).first()
        if examiner:
            attempt.examiner = examiner
            attempt.save()

    return redirect("home:dashboard")

@role_required(User.Role.ADMIN)
def explore_subjects(request):
    """
    This is for the page that will contain subject related options
    such as creating a new subject, editing an existing subject, etc.
    Only accessible to admins."
    """
    # select_related, because the template shows each subject's author: the list
    # is unpaginated, so without it every row costs its own query.
    subjects = Subject.objects.select_related("created_by")
    return render(request, "exam/explore_subjects.html", {"subjects": subjects})

@role_required(User.Role.ADMIN)
def create_subject(request):
    """
    This is for the page that will help create a new subject for the admin."
    """
    form = SubjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        subject = form.save(commit=False)
        subject.created_by = request.user  # Set the creator of the subject
        subject.save()
        return redirect("exam:explore_subjects")  # Redirect to the subject center after creation
    return render(request, "exam/create_subject.html", {"form": form})


@role_required(User.Role.ADMIN)
def edit_subject(request, subject_id):
    """
    This is for the page that will help edit an existing subject for the admin."
    """
    subject = get_object_or_404(Subject, id=subject_id)
    form = SubjectForm(request.POST or None, instance=subject)
    if request.method == "POST" and form.is_valid():
        form.save()
    return redirect("exam:explore_subjects")

@role_required(User.Role.ADMIN)
def explore_exams(request):
    """
    This is for viewing all the exams that are available in the system.
    Only accessible to admins."
    """
    exams = Exam.objects.select_related("subject").order_by(
      Case(When(status=Exam.Status.DRAFT, then=0), default=1, output_field=IntegerField()),
      "exam_name",)
    return render(request, "exam/explore_exams.html", {"exams": exams})

@role_required(User.Role.ADMIN)
def add_exam(request):
    """
    This is for the page that will help create a new exam for the admin."
    """
    form = ExamForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        exam = form.save(commit=False)
        exam.created_by = request.user
        exam.status = (
            Exam.Status.PUBLISHED
            if request.POST.get("action") == "publish"
            else Exam.Status.DRAFT
        )
        exam.save()
        return redirect("exam:explore_exams")
    return render(request, "exam/add_exam.html", {"form": form})

@role_required(User.Role.ADMIN)
def edit_exam(request, exam_id):
    """
    View for editing an existing exam. Only accessible to admins."
    """
    exam = get_object_or_404(Exam, id=exam_id)
    form = ExamForm(request.POST or None, instance=exam)
    if request.method == "POST" and form.is_valid():
        exam = form.save(commit=False)
        exam.status = (
            Exam.Status.PUBLISHED
            if request.POST.get("action") == "publish"
            else Exam.Status.DRAFT
        )
        exam.save()
        return redirect("exam:explore_exams")
    return render(request, "exam/add_exam.html", {"form": form})

@role_required(User.Role.ADMIN)
def add_question(request):
    """
    This is for the page that will help create a new question for the admin."
    """
    form = QuestionForm(request.POST or None, request.FILES or None, user=request.user)

    # request.FILES here too — each option can carry its own image and audio,
    # and a FileInput reads only from `files`. form_kwargs reaches every child
    # form: created_by is non-nullable on an option and on each media row it
    # may create, and a formset has no idea who is logged in.
    #
    # instance=form.instance rather than a fresh Question: it is the same object
    # the form fills in during _post_clean, so by the time the formset validates
    # its clean() can read the question_type that was actually submitted.
    formset = AnswerOptionFormSet(
        request.POST or None,
        request.FILES or None,
        instance=form.instance,
        form_kwargs={"user": request.user},
    )

    if request.method == "POST":
        # Validated in this order, and as two statements. form.is_valid() is
        # what populates form.instance, so the formset has to be asked second.
        # Written as `form.is_valid() and formset.is_valid()` it would
        # short-circuit — the author would fix the question, post again, and
        # only then be told about the options.
        form_ok = form.is_valid()
        formset_ok = formset.is_valid()

        if form_ok and formset_ok:
            # One transaction. A question saved without its options can be
            # served with nothing to pick from, so if the options fail the
            # question and its media rows go back with them.
            with transaction.atomic():
                question = form.save()
                # formset.instance is the same object, now with a pk, so
                # save() fills in each option's FK for us. created_by and the
                # option's media are handled inside AnswerOptionForm.save().
                formset.save()
            return redirect("exam:question_bank")

    return render(
        request,
        "exam/add_question.html",
        {
            "form": form,
            "formset": formset,
            # So each upload's byline states the limit the form actually
            # enforces, rather than a number typed into the markup.
            "max_image_mb": exam_forms.MAX_IMAGE_MB,
            "max_audio_mb": exam_forms.MAX_AUDIO_MB,
            "max_video_mb": exam_forms.MAX_VIDEO_MB,
        },
    )


@role_required(User.Role.ADMIN)
def question_bank(request):
    """
    This is for the page that will show all the questions available in the system.
    Only accessible to admins."
    """
    # select_related for the one-to-ones the card reads, prefetch_related for
    # the two collections. Without them each card costs its own queries for its
    # subject, its options and the exams in its "Attached to" list — and the
    # list is unpaginated, so that grows with the bank.
    questions = Question.objects.select_related(
        "created_by",
        "question_subject",
        "associated_image",
        "associated_audio",
        "associated_video",
    ).prefetch_related(
        "answers",
        "question_subject__exams",
    ).order_by(
        Case(When(status=Question.Status.ACTIVE, then=0), default=1, output_field=IntegerField()),
        "created_at"
    )
    return render(request, "exam/question_bank.html", {"questions": questions})

#: Where a parsed-but-unconfirmed import waits between the two requests.
#:
#: The session, not the cache. A browser cannot re-post a file the author
#: picked a request ago without them picking it again, so the rows have to be
#: kept somewhere — and SESSION_ENGINE here is the database backend, so this is
#: a row in Postgres, not anything in the cookie. LocMemCache would have been
#: wrong: it is per-process, so with more than one worker the confirm can land
#: somewhere that has never seen the upload.
IMPORT_SESSION_KEY = "question_import"


@role_required(User.Role.ADMIN)
def import_questions(request):
    """
    Bulk import, in two phases against one URL.

    Uploading parses the file and shows what *would* happen; a second submit
    commits it. Importing on the first click gives an author no way to notice
    they picked last month's file until two hundred questions are in the bank,
    and there is no bulk undo.

    The parsing lives in imports.py, which knows nothing about requests. This
    view only decides which phase it is in, and where the rows wait in between.
    """
    # Phase 2 first. The confirm posts only `action` and `token`, never a file,
    # so it would fail ImportQuestionsForm validation if it fell through to the
    # upload handling below.
    if request.method == "POST" and request.POST.get("action") == "import":
        return _commit_question_import(request)

    # Phase 1 — a file has just been uploaded, or this is a fresh page.
    #
    # One form object, used for both. Re-rendering with a *new* unbound form
    # would throw away the author's errors and their subject choice.
    form = ImportQuestionsForm(request.POST or None, request.FILES or None)
    preview = None

    if request.method == "POST" and form.is_valid():
        rows = form.parsed_rows()

        # A token, so a stale preview cannot be confirmed. Two tabs, or the
        # back button onto an earlier preview, would otherwise import whatever
        # the session happens to hold rather than what is on screen.
        token = secrets.token_urlsafe(8)
        request.session[IMPORT_SESSION_KEY] = {
            "token": token,
            "subject": form.cleaned_data["subject"].pk,
            # asdict, because the session serialises as JSON and a dataclass is
            # not JSON. _commit_question_import rebuilds them on the way out.
            "rows": [asdict(row) for row in rows],
        }

        preview = {
            "rows": rows,
            "valid": sum(1 for row in rows if not row.errors),
            "invalid": sum(1 for row in rows if row.errors),
            "unknown": form.unknown_columns,
            "token": token,
        }

    return render(
        request,
        "exam/import_questions.html",
        {
            "form": form,
            "preview": preview,
            # Passed through rather than typed into the markup, so what the
            # byline promises and what read_csv enforces cannot drift apart.
            "max_rows": imports.MAX_ROWS,
            "max_mb": imports.MAX_SIZE // 1024 // 1024,
        },
    )


def _commit_question_import(request):
    """
    Writes the rows the author has just seen and confirmed.

    Not a view of its own — no URL points here. Split out because
    import_questions() would otherwise do two unrelated jobs in one body, and
    the confirm path shares none of the upload path's logic.
    """
    stashed = request.session.get(IMPORT_SESSION_KEY)

    if not stashed or stashed.get("token") != request.POST.get("token"):
        messages.error(
            request,
            "That import is no longer available — it may have expired, or been "
            "confirmed already. Upload the file again.",
        )
        return redirect("exam:import_questions")

    subject = get_object_or_404(Subject, pk=stashed["subject"])
    rows = [imports.ParsedRow(**row) for row in stashed["rows"]]

    # Dropped before the write, not after. A reload of the redirect must not
    # import everything a second time, and if the write fails halfway the
    # author should re-upload rather than retry a half-applied import.
    del request.session[IMPORT_SESSION_KEY]

    created, failures = imports.import_rows(rows, subject, request.user)
    skipped = sum(1 for row in rows if row.errors)

    if created:
        messages.success(
            request,
            f"Imported {created} question{'' if created == 1 else 's'} "
            f"into {subject.name}.",
        )
    else:
        messages.error(request, "Nothing was imported.")

    if skipped:
        messages.warning(
            request,
            f"{skipped} row{'' if skipped == 1 else 's'} had problems and "
            f"{'was' if skipped == 1 else 'were'} skipped.",
        )

    # Rows that looked fine on the preview and failed anyway. parse_row never
    # touches the database, so anything that needs one only surfaces here.
    for number, problems in failures:
        messages.warning(request, f"Row {number}: {' '.join(problems)}")

    return redirect("exam:question_bank")

@role_required(User.Role.ADMIN)
def delete_question(request, question_id):
    pass

@login_required
def start_exam_termsandconditions(request, booking_id):
    """
    The instructions a candidate reads immediately before their exam.

    Everything the page shows — exam name, question count, pass mark, their
    scheduled time — comes off the booking, so the route carries its id.

    The ownership filter is part of the lookup, not a check afterwards, so
    somebody else's booking id is a 404 rather than a 403. We do not confirm a
    booking exists to a candidate with no business knowing. Same shape as
    reschedule() and cancel_booking().
    """
    booking = get_object_or_404(
        ExamBooking.objects.select_related("exam__subject"),
        booking_id=booking_id,
        candidate=request.user,
        status=ExamBooking.Status.BOOKED,
    )

    # POST is the begin button. It has to be a POST: it draws the paper and
    # starts the clock, and a GET that does that is one browser prefetch or one
    # link preview away from starting somebody's exam without them.
    if request.method == "POST":
        try:
            _start_or_resume(booking)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect("exam:start_exam_termsandconditions", booking_id=booking.booking_id)
        return redirect("exam:exam_player", booking_id=booking.booking_id)

    return render(
        request,
        "exam/start_exam_termsandconditions.html",
        {"booking": booking},
    )


def _start_or_resume(booking):
    """
    Returns the booking's ExamSheet, drawing the paper the first time.

    Idempotent on purpose. A candidate who double-clicks begin, or reloads the
    POST, or comes back after a dropped connection must land on the *same*
    paper — so an existing sheet is returned untouched rather than redrawn. The
    OneToOneField would refuse a second row anyway; returning early means they
    get their exam back instead of a 500.

    Everything is fixed here and never again: which questions, their order,
    what each is worth, and when the paper closes.
    """
    sheet = ExamSheet.objects.filter(booking=booking).first()
    if sheet is not None:
        return sheet

    # The join window, checked only for a NEW paper — after the resume above, on
    # purpose. Someone who began at 10:40 and lost their connection must get back
    # in at 10:50 even though nobody may start one then.
    #
    # Enforced here, not only by the disabled buttons: those are display, and
    # the begin POST can be sent without ever seeing them.
    now = timezone.now()
    if now < booking.scheduled_at:
        raise ValidationError(
            "This exam has not opened yet. You can begin from your scheduled time."
        )
    if now >= booking.join_closes_at:
        raise ValidationError(
            "The time to start this exam has passed."
        )

    exam = booking.exam

    # The ROUND's type, not the exam's. An exam can be "both", but a question is
    # only ever objective or subjective — filtering on the exam's format matched
    # nothing and every two-round exam refused to start.
    #
    # Read from the booking rather than derived: the booking already knows which
    # round it is, and the subjective row of a two-round attempt is
    # indistinguishable from a subjective-only exam's booking by format alone.
    round_type = booking.round_type

    pool = Question.objects.filter(
        question_subject=exam.subject,
        question_type=round_type,
        status=Question.Status.ACTIVE,
    )

    # A subjective round is one question, whatever the exam says. question_count
    # describes the objective round and is null on a subjective-only exam, so
    # reading it here refused to draw a paper that was perfectly well configured.
    wanted = (
        Exam.SUBJECTIVE_QUESTION_COUNT
        if round_type == Exam.Type.SUBJECTIVE
        else (exam.question_count or 0)
    )
    if not wanted:
        raise ValidationError(
            "This exam has no question count set, so there is no paper to draw. "
            "Please contact support."
        )

    available = pool.count()
    if available < wanted:
        # Checked at Start Test rather than only at publish, because the bank
        # changes after an exam is saved — a form check would have gone stale.
        raise ValidationError(
            f"This exam needs {wanted} questions but only {available} are "
            f"available. Please contact support before trying again."
        )

    # order_by("?") is a database-side shuffle. Fine at this scale; if the bank
    # ever reaches the tens of thousands it becomes a full sort and should be
    # replaced by sampling ids in Python.
    drawn = list(pool.order_by("?")[:wanted])

    with transaction.atomic():
        sheet = ExamSheet.objects.create(
            booking=booking,
            # The round's own clock: 45 minutes for an objective sitting, 36
            # hours for a subjective window. exam.duration_minutes is the total
            # across both rounds — 2205 for a "both" exam — and would have given
            # a candidate 37 hours to answer forty multiple-choice questions.
            expires_at=timezone.now() + timedelta(
                minutes=Exam.DURATION_BY_TYPE[round_type]
            ),
        )
        ExamSheetQuestion.objects.bulk_create([
            ExamSheetQuestion(
                sheet=sheet,
                question=question,
                position=index,
                marks=question.marks,
            )
            for index, question in enumerate(drawn, start=1)
        ])
    return sheet

@login_required
def exam_player(request, booking_id):
    """
    The exam itself: one question at a time, with a palette to jump around.

    Reached only from the instructions page, which is what creates the sheet.
    Arriving here without one means the candidate has not pressed begin, so
    they are sent back rather than having a paper drawn for them by a URL they
    typed.

    ANSWER KEYS NEVER REACH THIS PAGE. The payload below is built field by
    field and `is_correct` is not one of them — a serializer shared with
    grading is how that leaks. See docs/conventions.md, "Answer-key safety".

    Objective rounds only. Autosave (save_answer) writes selected_option and
    flagged per question, and this view hands both back so a rejoin resumes
    where the candidate left off. The subjective round has its own page,
    exam_player_subjective.
    """
    booking = get_object_or_404(
        ExamBooking.objects.select_related("exam__subject"),
        booking_id=booking_id,
        candidate=request.user,
    )
    sheet = (
        ExamSheet.objects
        .filter(booking=booking)
        .prefetch_related("questions__question__answers")
        .first()
    )
    if sheet is None:
        return redirect("exam:start_exam_termsandconditions", booking_id=booking.booking_id)

    if sheet.submitted_at is not None:
        messages.info(request, "You have already submitted this exam.")
        return redirect("home:dashboard")

    # Serialised here rather than in the template so the shape is visible in
    # one place and the answer key is excluded by construction.
    questions = []
    for entry in sheet.questions.all():
        # One dict per option, so an id can never drift from its text the way
        # two parallel lists could. Autosave sends the id back, not the index,
        # so a reorder between reads cannot change what was chosen. Built field
        # by field: an id says nothing about correctness, and is_correct stays
        # out of this payload.
        options = [
            {"id": o.id, "text": o.answer_option_text}
            for o in entry.question.answers.all()
        ]

        # What autosave stored, handed back so a rejoin shows it. The player
        # tracks the choice as a position in `options`, so the saved id is
        # turned into that index here. Matched by id against this read's list,
        # which is what keeps it right even if the order differs from the last
        # page load. None when unanswered — or if the option is somehow no
        # longer among the question's answers, which shows as blank rather
        # than as the wrong option ticked.
        answer = next(
            (i for i, o in enumerate(options) if o["id"] == entry.selected_option_id),
            None,
        )

        questions.append({
            "n": entry.position,
            "type": entry.question.question_type,
            "marks": entry.marks,
            "text": entry.question.question_text,
            "options": options,
            "answer": answer,
            "flagged": entry.flagged,
        })

    remaining = int((sheet.expires_at - timezone.now()).total_seconds())

    return render(
        request,
        "exam/exam_player.html",
        {
            "booking": booking,
            "sheet": sheet,
            "questions_json": questions,
            # Clamped at zero so an expired sheet renders 00:00 rather than a
            # negative countdown. The server, not this number, is what actually
            # decides whether the paper is still open.
            "remaining_seconds": max(0, remaining),
            "start_position": sheet.current_position,
        },
    )

@login_required
def exam_player_subjective(request, booking_id):
    """
    This is the exam player for subjective exams. It is similar to the exam_player view but tailored for subjective paper.
    A subjective paper will have only one question and a textbox where github PR can be pasted.
    If the paste is complete, the candidate can submit the exam. They can access this player until 36 hours after starting.
    """
    booking = get_object_or_404(
        ExamBooking.objects.select_related("exam__subject"),
        booking_id=booking_id,
        candidate=request.user,
    )
    # .first(), not the bare filter: filter() returns a QuerySet — a list-like
    # of sheets, never None — and a QuerySet has no .questions.
    exam_sheet = ExamSheet.objects.filter(booking=booking).first()
    if exam_sheet is None:
        # No sheet means the candidate has not pressed begin yet; the
        # instructions page is where the paper is drawn.
        return redirect("exam:start_exam_termsandconditions", booking_id=booking.booking_id)

    # exam_sheet.questions is the related manager — every question row on this
    # sheet — not a question itself. A subjective paper has one row; take it,
    # with its Question in the same query.
    entry = exam_sheet.questions.select_related("question").first()
    if entry is None:
        messages.error(request, "No question found for this subjective exam. Please contact support.")
        return redirect("home:dashboard")

    # Already answered: say so rather than offer the form again. A second
    # SubjectiveSubmission for the same entry would break the one-to-one and
    # surface as a 500. Checked again under a lock on POST below — this one
    # only spares the candidate a form they cannot use.
    if SubjectiveSubmission.objects.filter(entry=entry).exists():
        messages.info(request, "You have already submitted this exam.")
        return redirect("home:dashboard")

    expires_at = exam_sheet.expires_at
    if expires_at < timezone.now():
        messages.error(request, "The time to submit this exam has passed. Please contact support or check My Assessments section.")
        return redirect("home:dashboard")

    form = ExamSheetFormSubjective(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            # Locks the sheet row until the transaction ends, as submit_exam
            # does. Two POSTs at once (a double click) both passed the check
            # above; the second now waits here, then finds the first one's
            # submission and stops instead of crashing on the one-to-one.
            ExamSheet.objects.select_for_update().get(pk=exam_sheet.pk)
            if SubjectiveSubmission.objects.filter(entry=entry).exists():
                messages.info(request, "You have already submitted this exam.")
                return redirect("home:dashboard")

            # commit=False builds the SubjectiveSubmission from the three form
            # fields without writing it. entry is deliberately not a form field
            # — the browser must not choose which paper an answer belongs to —
            # so the view sets it from the candidate's own sheet, then saves.
            submission = form.save(commit=False)
            submission.entry = entry
            submission.save()

        messages.success(request, "Your answer has been submitted.")
        return redirect("home:dashboard")
    else:
        # The objects themselves, under the names the template documents:
        # it reads sheet.expires_at for the deadline, and question.marks and
        # question.question.question_text for the task. A bound form that
        # failed validation carries its errors and the candidate's values back.
        return render(
            request,
            "exam/exam_player_subjective.html",
            {
                "form": form,
                "booking": booking,
                "sheet": exam_sheet,
                "question": entry,
            },
        )


@login_required
@require_POST
def save_answer(request, booking_id):
    """
    Autosave: records one answer, and the candidate's place, as they go.

    Called by the player in the background, so it answers in JSON rather than
    redirecting — the page stays where it is and only the "Saved" tick reacts.
    The tick should appear on {"ok": true} and nowhere else; a receipt shown
    before the server confirms is the one that lied before.

    Objective rounds only — a subjective answer is a SubjectiveSubmission,
    saved by its own page. Told apart by which fields were sent:
      option_id  – an objective answer; empty clears it
      flagged    – "true"/"false", the review mark; alone or with an answer
      neither    – navigation, which only moves current_position

    Refuses once the paper is closed — submitted, past expires_at, or the
    booking no longer live — so nothing can change an answer after the fact.
    """
    form = SaveAnswerForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": form.errors}, status=400)
    data = form.cleaned_data

    with transaction.atomic():
        booking = get_object_or_404(
            ExamBooking,
            booking_id=booking_id,
            candidate=request.user,
        )
        # Locked for the same reason submit_exam locks it: a save racing the
        # final submit must land before it or not at all, never after the
        # paper was graded.
        sheet = (
            ExamSheet.objects
            .select_for_update()
            .filter(booking=booking)
            .first()
        )
        if sheet is None:
            return JsonResponse({"ok": False, "error": "no_sheet"}, status=404)

        # 409 Conflict: the request was fine, the paper's state refuses it. The
        # player should stop saving and let the submit path take over.
        if (
            sheet.submitted_at is not None
            or timezone.now() >= sheet.expires_at
            or booking.status != ExamBooking.Status.BOOKED
        ):
            return JsonResponse({"ok": False, "error": "closed"}, status=409)

        entry = (
            ExamSheetQuestion.objects
            .select_related("question")
            .filter(sheet=sheet, position=data["position"])
            .first()
        )
        if entry is None:
            return JsonResponse({"ok": False, "error": "no_such_question"}, status=400)

        fields = []

        if "option_id" in request.POST:
            if entry.question.question_type != Question.Type.OBJECTIVE:
                return JsonResponse({"ok": False, "error": "wrong_type"}, status=400)
            option = None
            if data["option_id"] is not None:
                # Filtered by this question, so an id belonging to some other
                # question — on this paper or any other — is refused rather
                # than stored. Without it a candidate could save any option id
                # in the database against question 3.
                option = entry.question.answers.filter(pk=data["option_id"]).first()
                if option is None:
                    return JsonResponse({"ok": False, "error": "no_such_option"}, status=400)
            entry.selected_option = option
            fields.append("selected_option")

        # Separate from the option check above: a flag can arrive on its own or alongside an
        # answer. Checked against request.POST, not cleaned_data — the form
        # turns "not sent" into False, which would unflag the question on
        # every answer save.
        if "flagged" in request.POST:
            entry.flagged = data["flagged"]
            fields.append("flagged")

        if fields:
            # update_fields writes only the columns this request named. marks
            # and marks_awarded are never touched by a candidate's request.
            entry.save(update_fields=fields)

        sheet.current_position = entry.position
        sheet.save(update_fields=["current_position"])

    return JsonResponse({"ok": True})


def grade_exam(booking, sheet):
    """
    Grades the exam after submission.
    """
    if booking.round_type == Exam.Type.OBJECTIVE:
        # Grade the exam only if it's an objective exam.
        marks_obtained = 0
        questions = ExamSheetQuestion.objects.filter(sheet=sheet).select_related("question", "selected_option")
        for question in questions:
            if question and question.selected_option and question.selected_option.is_correct:
                question.marks_awarded = question.marks
                marks_obtained += question.marks
            else:
                question.marks_awarded = 0
            question.save()
        booking.marks_obtained = marks_obtained
        booking.save()
        return marks_obtained
    elif booking.round_type == Exam.Type.SUBJECTIVE:
        # Subjective exams are graded manually
        pass


@login_required
@require_POST
def submit_exam(request, booking_id):
    """
    Marks the exam as completed and submitted. Triggered on multiple ocassion:
    When the user selects submit
    When the time is up and the user was idle
    When the time is up and the user was active on the sheet

    POST only — it ends an exam, so a link, a prefetch or the back button must
    not be able to trigger it.
    """
    # One transaction for everything below: stamping the sheet, moving the
    # booking on, grading and booking the subjective round. A failure part way
    # leaves the paper open rather than half-submitted.
    with transaction.atomic():
        booking = get_object_or_404(
            ExamBooking.objects.select_related("exam__subject"),
            booking_id=booking_id,
            candidate=request.user,
        )
        # select_for_update locks the sheet row until the transaction ends. A
        # double click or the timer firing just after Submit sends two POSTs;
        # the second waits here, then sees submitted_at already set below.
        sheet = (
            ExamSheet.objects
            .select_for_update()
            .filter(booking=booking)
            .first()
        )
        if sheet is None:
            messages.error(request, "No exam sheet found for this booking.")
            return redirect("home:dashboard")

        # Already finished — a repeat POST, not a second submission. Without this
        # a Both exam would try to create a second subjective booking.
        if sheet.submitted_at is not None:
            messages.info(request, "You have already submitted this exam.")
            return redirect("home:dashboard")

        # Only a live booking can be sat. A cancelled or no-show booking that
        # still has a sheet must not be turned into an attended one.
        if booking.status != ExamBooking.Status.BOOKED:
            messages.error(request, "This booking is not open for submission.")
            return redirect("home:dashboard")

        now = timezone.now()
        # The server's clock decides, not the browser's. A POST after expiry is
        # still accepted — refusing it would leave the paper open forever — but
        # it is recorded as ending at the deadline, as the model asks.
        sheet.submitted_at = min(now, sheet.expires_at)

        # Only the Submit button before the deadline counts as the candidate's
        # own submission. The JS timeout posts no action, and anything arriving
        # after expires_at is a timeout whatever the form said.
        if request.POST.get("action") == "submit_action" and now < sheet.expires_at:
            sheet.submission_status = ExamSheet.SubmissionStatus.SELF
        else:
            sheet.submission_status = ExamSheet.SubmissionStatus.TIMEDOUT
        sheet.save()
        # Update the booking status to attended
        booking.status = ExamBooking.Status.ATTENDED
        booking.save()
        marks_obtained = grade_exam(booking, sheet)
        # create a new booking if the exam is a two-round exam and the current round is objective
        is_first_of_two = (
            booking.exam.exam_type == Exam.Type.BOTH
            and booking.round_type == Exam.Type.OBJECTIVE
        )
        if is_first_of_two:
            ExamBooking.objects.create(
                candidate=booking.candidate,
                exam=booking.exam,
                round_type=Exam.Type.SUBJECTIVE,
                status=ExamBooking.Status.BOOKED,
                parent_booking=booking,  # Link the new booking to the original one
                booked_timezone=booking.booked_timezone,
                scheduled_at=sheet.submitted_at + timedelta(minutes=Exam.ROUND_GAP_MINUTES),
            )

    # Messages after the transaction, so a rollback never leaves a success banner
    # for a submission that did not happen.
    messages.success(request, "Your exam has been submitted successfully.")
    if is_first_of_two:
        messages.info(request, "Your objective round is completed. You have been booked for the subjective round.")
    else:
        messages.info(request, "Thank you for completing the exam.")
    # Every round ends on the completed page now, including the first round of
    # a two-round exam — that candidate is the one who needs telling where the
    # second round is.
    candidate_name = booking.candidate.get_full_name()
    marks_obtained = booking.marks_obtained
    # The round, not exam.exam_type: on a two-round exam the type is "both"
    # for both bookings, so it cannot say whether this paper was objective.
    round_type = booking.round_type
    # Keyword arguments, not a dict: exam_completed collects them through
    # **kwargs, which accepts keywords only — a dict passed positionally
    # raises TypeError.
    return exam_completed(
        request,
        candidate_name=candidate_name,
        marks_obtained=marks_obtained,
        round_type=round_type,
        has_next_round=is_first_of_two,
    )
    # return redirect("exam:exam_completed", {"candidate_name": candidate_name, "marks_obtained": marks_obtained})

@login_required
def exam_completed(request, **kwargs):
    """
    Displays a confirmation page after the exam is completed.
    """
    return render(request, "exam/exam_completed.html", kwargs)
