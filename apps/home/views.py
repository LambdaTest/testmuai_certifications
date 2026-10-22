"""
Cross-cutting pages — the candidate dashboard and, later, account settings.

Anything about certifications, booking, sitting an exam, grading, or
credentials belongs in ``apps.exam``.
"""

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import Http404, StreamingHttpResponse
from django.utils import timezone

from apps.exam.calendar import google_calendar_url
from apps.exam.models import ExamBooking

from . import exports
from .forms import ExportCandidatesForm
from .models import User
from .decorators import role_required
from django.shortcuts import get_object_or_404


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
    # upcoming(), not scheduled_at >= now: that dropped a booking off the
    # dashboard the moment it started — exactly when the candidate needs its
    # Join button. upcoming() keeps it until the join window closes, the same
    # rule as My Assessments and the assessment page's badge.
    #
    # ExamBooking orders newest-first by default, so ask for the other
    # direction explicitly — we want the nearest one, not the furthest.
    return (
        ExamBooking.objects.filter(candidate=user)
        .upcoming()
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
        exams_underway = ExamBooking.objects.filter(status=ExamBooking.Status.ATTENDED).count()
        awaiting_grading = ExamBooking.objects.filter(status=ExamBooking.Status.UNDER_REVIEW).count()
        upcoming_exams = ExamBooking.objects.filter(status=ExamBooking.Status.BOOKED, scheduled_at__gte=timezone.now()).count()
        return render(request, 
                      "home/dashboard_admin.html", 
                      {"user_name": user_name, "user_role": user_role, 
                       "exams_underway": exams_underway, "awaiting_grading": awaiting_grading, "upcoming_exams": upcoming_exams})
    elif user_role == User.Role.EXAMINER:
        # Its own template, not a variant of the admin one: an examiner should
        # be structurally unable to render admin controls.
        #
        # The same papers as My Tasks — assigned to them, still under review,
        # oldest submission first — but only a glance: the five that have
        # waited longest. The full queue is My Tasks. [:5] becomes LIMIT 5 in
        # the SQL, so a thousand pending papers still loads five rows; the
        # total comes from a separate COUNT, never from loading them all.
        pending = (
            request.user.assigned_bookings
            .filter(status=ExamBooking.Status.UNDER_REVIEW)
            .select_related("exam", "sheet")
            .order_by("sheet__submitted_at")
        )
        return render(
            request,
            "home/dashboard_examiner.html",
            {
                "user_name": user_name,
                "user_role": user_role,
                "pending_preview": pending[:5],
                "pending_count": pending.count(),
            },
        )
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

@role_required(User.Role.ADMIN)
def candidate_info(request):
    """
    Shows the candidate information to the admin: searched and paginated on
    the server, 25 to a page, so the page costs the same with 50 candidates or
    50,000.

    ?q= matches name, email, login id, phone, or a booking reference — the
    "Ref 198f572b" an examiner quotes from a grading page. That last match is
    what lets an admin turn a blind reference back into a person, and it is
    why the search runs here: the page itself never contains bookings.
    """
    q = request.GET.get("q", "").strip()
    candidates = User.objects.filter(role=User.Role.CANDIDATE)
    if q:
        candidates = candidates.filter(
            Q(display_name__icontains=q)
            | Q(email__icontains=q)
            | Q(external_id__icontains=q)
            | Q(contact_number__icontains=q)
            # bookings = ExamBooking.candidate's related_name. istartswith on
            # the UUID accepts the 8-character reference, any case.
            | Q(bookings__booking_id__istartswith=q)
        ).distinct()   # one candidate can match through several bookings
    candidates = candidates.order_by("display_name", "email")

    # get_page, not page: a missing, non-numeric or too-large ?page= falls back
    # to the first or last page instead of raising.
    page = Paginator(candidates, 25).get_page(request.GET.get("page"))
    return render(request, "home/candidate_info.html", {"candidates": page, "q": q})

@role_required(User.Role.ADMIN)
def candidate_detail(request, candidate_id):
    """
    Shows the candidate's details to the admin: personal info and all bookings.
    """
    candidate =  get_object_or_404(User, id=candidate_id, role=User.Role.CANDIDATE)
    bookings = ExamBooking.objects.filter(candidate=candidate).select_related("exam__subject", "cancelled_by").order_by("-scheduled_at")
    return render(request, "home/candidate_detail.html", {"candidate": candidate, "bookings": bookings})


@role_required(User.Role.ADMIN)
def export_candidates(request):
    """
    Candidate Center → Export Candidates: a CSV of candidates or of bookings.

    One view, both halves, on GET — exporting changes nothing, and the URL
    keeps the filters:

      - no `download` in the query → the page, with an empty form
      - `download` present        → validate, then send the file; or show the
                                    page again with the errors, or with
                                    "Nothing matches" rather than an empty file

    Filters (exam, From/To in IST) mean the same in both exports. For
    candidates they apply to one booking at a time: "Selenium in October"
    is a candidate with a Selenium booking in October, not one with any
    Selenium booking and any October booking. With no filter at all, every
    candidate is listed — including those who never booked.

    Admin-only, like Candidate Info: this is the file that takes names,
    emails and phones out of the system. What goes in it is the admin's
    choice, from the fixed lists in apps.home.exports.
    """
    downloading = "download" in request.GET
    form = ExportCandidatesForm(request.GET if downloading else None)
    nothing_matches = False

    if downloading and form.is_valid():
        kind = form.cleaned_data["kind"]
        exam = form.cleaned_data["exam"]
        date_from = form.cleaned_data["date_from"]

        # The booking filters, as Q objects relative to a booking. `prefix`
        # reaches them from a User ("bookings__") for the candidate export.
        def booking_filter(prefix=""):
            q = Q()
            if exam is not None:
                q &= Q(**{f"{prefix}exam": exam})
            if date_from is not None:
                start, end = exports.ist_day_bounds(date_from, form.cleaned_data["date_to"])
                q &= Q(**{f"{prefix}scheduled_at__gte": start, f"{prefix}scheduled_at__lt": end})
            return q

        filtered = exam is not None or date_from is not None

        if kind == "candidates":
            # Count with a filter keeps both conditions on the same booking
            # row, which is what makes "Selenium in October" mean one booking.
            rows = (
                User.objects.filter(role=User.Role.CANDIDATE)
                .exclude(email__isnull=True).exclude(email="")
                .annotate(export_bookings=Count("bookings", filter=booking_filter("bookings__"), distinct=True))
                .order_by("email")
            )
            if filtered:
                rows = rows.filter(export_bookings__gt=0)
        else:
            rows = (
                ExamBooking.objects.filter(candidate__role=User.Role.CANDIDATE)
                .exclude(candidate__email__isnull=True).exclude(candidate__email="")
                .filter(booking_filter())
                .select_related("candidate", "exam", "booked_by", "cancelled_by", "graded_by")
                .order_by("scheduled_at", "candidate__email")
            )

        if rows.exists():
            filename = f"{kind}-{exports.today_ist():%Y-%m-%d}.csv"
            response = StreamingHttpResponse(
                # iterator(): rows are read from the database in chunks as the
                # file is written, never all at once.
                exports.csv_rows(kind, form.chosen_columns(), rows.iterator(chunk_size=2000)),
                content_type="text/csv; charset=utf-8",
            )
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response
        nothing_matches = True

    return render(
        request,
        "home/export_candidates.html",
        {
            "form": form,
            "nothing_matches": nothing_matches,
            "candidate_locked": [h for h, _ in exports.CANDIDATE_LOCKED.values()],
            "booking_locked": [h for h, _ in exports.BOOKING_LOCKED.values()],
            "export_timezone": exports.EXPORT_TIMEZONE,
        },
    )
