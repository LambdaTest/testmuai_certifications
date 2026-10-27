"""
The variables every email template receives.

Times are formatted here, as text, in the zone the candidate booked in —
not left to the template's |date filter, which would convert them back to
the server's zone (UTC) and show a 10:00 IST exam as 04:30.

Links are absolute (settings.SITE_URL): a relative link means nothing in an
inbox.
"""

from django.conf import settings
from django.urls import reverse

from apps.exam.timezones import to_local


def _link(name, **kwargs):
    return settings.SITE_URL + reverse(name, kwargs=kwargs)


def _when(moment, tz):
    """"Saturday, 24 October 2026 at 10:00 AM" — in the booking's own zone."""
    local = to_local(moment, tz)
    hour = local.strftime("%I").lstrip("0")
    return f"{local:%A}, {local.day} {local:%B %Y} at {hour}:{local:%M %p}"


def build_context(row, booking, now):
    candidate = booking.candidate
    minutes_until = max(0, round((booking.scheduled_at - now).total_seconds() / 60))
    return {
        "first_name": ((candidate.display_name or "").split(" ")[0] if candidate else "") or "there",
        "exam_name": booking.exam.exam_name,
        "round_label": booking.get_round_type_display(),
        "is_subjective": booking.round_type == "subjective",
        # The second round of a two-round exam, which the system booked.
        "is_second_round": booking.parent_booking_id is not None,
        "when": _when(booking.scheduled_at, booking.booked_timezone),
        "closes": _when(booking.join_closes_at, booking.booked_timezone),
        "timezone": booking.booked_timezone,
        "duration": booking.duration_display,
        "minutes_until": minutes_until,
        "ref": str(booking.booking_id)[:8],
        "booking_url": _link("exam:explore_assessment", booking_id=booking.booking_id),
        "join_url": _link("exam:start_exam_termsandconditions", booking_id=booking.booking_id),
        "book_again_url": settings.SITE_URL + reverse("exam:book") + f"?exam={booking.exam.slug}",
        "change_cutoff_minutes": settings.BOOKING_CHANGE_CUTOFF_MINUTES,
        "reply_to": settings.EMAIL_REPLY_TO,
        "site_url": settings.SITE_URL,
    }
