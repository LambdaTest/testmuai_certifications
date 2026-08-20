"""
Cross-cutting pages — the candidate dashboard and, later, account settings.

Anything about certifications, booking, sitting an exam, grading, or
credentials belongs in ``apps.exam``.
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.utils import timezone

from apps.exam.calendar import google_calendar_url
from apps.exam.models import ExamBooking

from .models import User


def _countdown(scheduled_at, now=None):
    """
    How far away a booking is, phrased for the dashboard card.

        under 60 minutes   ->  "In 45 minutes"
        up to 20 hours     ->  "In 6 hours"
        over 20 hours      ->  "In 2 days"

    Both arguments are timezone-aware UTC; the wording is the same whatever
    timezone the candidate booked in.
    """
    now = now or timezone.now()
    minutes = (scheduled_at - now).total_seconds() / 60

    if minutes <= 0:
        return "Now"

    if minutes < 60:
        value, unit = max(1, round(minutes)), "minute"
    elif minutes <= 20 * 60:
        value, unit = max(1, round(minutes / 60)), "hour"
    else:
        value, unit = max(1, round(minutes / (60 * 24))), "day"

    return f"In {value} {unit}{'' if value == 1 else 's'}"


def _next_booking(user):
    """The candidate's soonest upcoming booking, or None."""
    # ExamBooking orders newest-first by default, so ask for the other
    # direction explicitly — we want the nearest one, not the furthest.
    return (
        ExamBooking.objects.filter(
            candidate=user,
            status=ExamBooking.Status.BOOKED,
            scheduled_at__gte=timezone.now(),
        )
        .select_related("exam__subject")
        .order_by("scheduled_at")
        .first()
    )

@login_required
def dashboard(request):
    # The template is still static sample markup. Each block that should read
    # real data names its context variable in a comment above it.
    try:
        user_role = request.user.role
        user_name = request.user.display_name
        user_name = user_name.split(" ")[0]  # Get first name only
    except AttributeError:
        user_role = None
        user_name = None
    # Compared against User.Role rather than string literals — the stored value
    # is "admin" while the label is "Admin", and comparing to the label gives a
    # branch that silently never matches.
    if user_role == User.Role.ADMIN:
        exams_underway = ExamBooking.objects.filter(status=ExamBooking.Status.ATTENDED, scheduled_at__gte=timezone.now()).count()
        awaiting_grading = ExamBooking.objects.filter(status=ExamBooking.Status.UNDER_REVIEW).count()
        upcoming_exams = ExamBooking.objects.filter(status=ExamBooking.Status.BOOKED, scheduled_at__gte=timezone.now()).count()
        return render(request, 
                      "home/dashboard_admin.html", 
                      {"user_name": user_name, "user_role": user_role, 
                       "exams_underway": exams_underway, "awaiting_grading": awaiting_grading, "upcoming_exams": upcoming_exams})
    elif user_role == User.Role.EXAMINER:
        # Its own template, not a variant of the admin one: an examiner should
        # be structurally unable to render admin controls.
        return render(request, "home/dashboard_examiner.html", {"user_name": user_name, "user_role": user_role})
    elif user_role == User.Role.CANDIDATE:
        booking = _next_booking(request.user)
        return render(
            request,
            "home/dashboard_candidate.html",
            {
                "user_name": user_name,
                "user_role": user_role,
                # None when nothing is booked — the template shows the
                # "No exam scheduled yet" state instead.
                "upcoming_booking": booking,
                "exam_name": booking.exam.exam_name if booking else None,
                "exam_countdown": _countdown(booking.scheduled_at) if booking else None,
                # Google can only create an event — no UID in the URL — so the
                # .ics download is the one that can move or cancel it later.
                "gcal_url": google_calendar_url(booking) if booking else None,
            },
        )
    else:
        # Raising is what actually produces a 404 — Django then renders
        # templates/404.html with a 404 status. Rendering that template
        # directly would return HTTP 200 with a "not found" page on it.
        raise Http404("No dashboard for this role.")
    