"""
The booking page.

/book is the entry point into this app from the main TestMu AI site. It takes no
path parameter: the candidate chooses the certification from a selector, then
picks their own date and time.
"""

import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from . import timezones
from .calendar import build_ics
from .forms import BookingForm, RescheduleForm
from .models import Exam, ExamBooking


def _exam_payload():
    """Bookable certifications, as the client-side picker needs them."""
    return [
        {
            "slug": c.slug,
            "name": c.exam_name,
            "level": c.get_level_display(),
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

    booked = None
    form = BookingForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        # Candidate is None until the OIDC integration lands.
        booked = form.save(candidate=None)

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

    form = RescheduleForm(request.POST or None)
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
                        "level": exam.get_level_display(),
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