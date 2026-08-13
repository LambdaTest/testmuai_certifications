"""
Calendar invites for exam bookings.

One generator, used by the ``.ics`` download view and — later — by booking
confirmation, reschedule and cancellation emails. Two implementations would
drift, and a drifted UID silently breaks the update chain described below.

**The UID matters.** Every invite for a booking carries the same ``UID`` (the
booking's UUID). Send the same UID again with a higher ``SEQUENCE`` and the
candidate's calendar *moves* the existing event rather than adding a second
one; send it with ``STATUS:CANCELLED`` and the event disappears. Generate a
fresh UID per invite and a reschedule leaves a stale entry behind — which for
this product means someone turns up at the wrong time.
"""

from datetime import timedelta
from datetime import timezone as dt_timezone
from urllib.parse import urlencode

from django.utils import timezone

from .timezones import to_local

#: A calendar entry marks when the exam *starts*. A 45-minute objective exam is
#: a real appointment and blocks the right amount of time; a 36-hour subjective
#: assignment is a window with a deadline, and blocking a day and a half of
#: someone's calendar is not what they want. So the block is capped and the
#: real duration is spelled out in the description instead.
CALENDAR_BLOCK_MAX_MINUTES = 60

PRODID = "-//TestMu AI//Certifications//EN"


def _stamp(moment):
    """A UTC instant in iCalendar's compact form: 20260816T101500Z."""
    return moment.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _escape(text):
    """RFC 5545 escaping for TEXT values. Order matters — backslash first."""
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold(line):
    """
    Lines may not exceed 75 octets. Continuations start with a single space.
    Folding is done on bytes, not characters, or multi-byte text breaks.
    """
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line

    chunks, current = [], b""
    for char in line:
        encoded = char.encode("utf-8")
        limit = 75 if not chunks else 74  # continuations lose one octet to the space
        if len(current) + len(encoded) > limit:
            chunks.append(current)
            current = b""
        current += encoded
    chunks.append(current)
    return "\r\n ".join(c.decode("utf-8") for c in chunks)


def event_window(booking):
    """(start, end) for the calendar entry — see CALENDAR_BLOCK_MAX_MINUTES."""
    start = booking.scheduled_at
    minutes = min(booking.exam.duration_minutes, CALENDAR_BLOCK_MAX_MINUTES)
    return start, start + timedelta(minutes=minutes)


def _summary(booking):
    return booking.exam.exam_name


def _description(booking):
    exam = booking.exam
    parts = [
        f"{exam.get_exam_type_display()} exam · {exam.duration_minutes} minutes.",
    ]
    if exam.duration_minutes > CALENDAR_BLOCK_MAX_MINUTES:
        deadline = booking.scheduled_at + timedelta(minutes=exam.duration_minutes)
        local = to_local(deadline, booking.booked_timezone)
        parts.append(f"Submit by {local:%a, %d %b %Y %H:%M} {booking.booked_timezone}.")
    parts.append("Join from your TestMu AI Certifications dashboard.")
    return " ".join(parts)


def build_ics(booking, sequence=0, cancelled=False, url=""):
    """
    An iCalendar document for one booking.

    ``sequence`` increments on every change to an existing booking; ``cancelled``
    emits STATUS:CANCELLED so the calendar removes it. Both rely on the UID
    staying the same.
    """
    start, end = event_window(booking)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        # PUBLISH, not REQUEST: this is "here is an event", not an invitation
        # expecting an RSVP that nothing would receive.
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{booking.booking_id}",
        f"DTSTAMP:{_stamp(timezone.now())}",
        f"DTSTART:{_stamp(start)}",
        f"DTEND:{_stamp(end)}",
        f"SUMMARY:{_escape(_summary(booking))}",
        f"DESCRIPTION:{_escape(_description(booking))}",
        f"SEQUENCE:{sequence}",
        f"STATUS:{'CANCELLED' if cancelled else 'CONFIRMED'}",
    ]
    if url:
        lines.append(f"URL:{_escape(url)}")

    if not cancelled:
        lines += [
            "BEGIN:VALARM",
            "TRIGGER:-PT15M",
            "ACTION:DISPLAY",
            "DESCRIPTION:Your TestMu AI exam starts in 15 minutes",
            "END:VALARM",
        ]

    lines += ["END:VEVENT", "END:VCALENDAR"]

    # CRLF is required by the spec, and the document must end with one.
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def google_calendar_url(booking):
    """
    A "create event" link for Google Calendar.

    Note what it cannot do: there is no UID or SEQUENCE in this URL, so it can
    only ever *create*. A reschedule can't move an event added this way — only
    the .ics path can. That asymmetry is why both options exist.
    """
    start, end = event_window(booking)
    params = {
        "action": "TEMPLATE",
        "text": _summary(booking),
        "dates": f"{_stamp(start)}/{_stamp(end)}",
        "details": _description(booking),
        "ctz": booking.booked_timezone,
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(params)
