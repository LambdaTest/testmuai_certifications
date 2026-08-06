"""
The booking page.

/book is the entry point into this app from the main TestMu AI site. It takes no
path parameter: the candidate chooses the certification from a selector, then
picks their own date and time.
"""

import json

from django.conf import settings
from django.shortcuts import render

from . import timezones
from .forms import BookingForm
from .models import Certification


def _exam_payload():
    """Bookable certifications, as the client-side picker needs them."""
    return [
        {
            "slug": c.slug,
            "name": c.name,
            "level": c.get_level_display(),
            "description": c.description,
        }
        for c in Certification.objects.filter(status=Certification.Status.PUBLISHED)
    ]


def book(request):
    # Optional prefill hint from the main site. Its redirect carries TestMu AI's
    # own numeric course id (?id=2934); ?exam=<slug> is also accepted. A missing,
    # unknown or stale value falls back silently to "Choose an exam" — never an
    # error. Nothing depends on this working.
    hint = request.GET.get("exam") or request.GET.get("id")
    preselected = ""
    if hint:
        published = Certification.objects.filter(status=Certification.Status.PUBLISHED)
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
