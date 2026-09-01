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
from django.http import Http404, HttpResponse, request
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

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
    SubjectForm,
    ImportQuestionsForm
)
from .models import Exam, ExamBooking, Subject, Question, Audio, Video
from apps.home.models import User
from apps.home.decorators import role_required
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

    # Anonymous until OIDC lands, so the clash check is inert on this path.
    candidate = request.user if request.user.is_authenticated else None
    form = BookingForm(request.POST or None, candidate=candidate)

    if request.method == "POST" and form.is_valid():
        # Candidate is None until the OIDC integration lands.
        booking = form.save(candidate=None)
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
    questions = Question.objects.select_related("created_by", "associated_audio", "associated_video").order_by(
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
