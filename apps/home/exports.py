"""
Candidate Center → Export Candidates: what can go in the CSV, and how it is
written.

Two exports, one per download:

  - "candidates" — one row per candidate          (CANDIDATE_COLUMNS)
  - "bookings"   — one row per booking (sitting)  (BOOKING_COLUMNS)

Each column list is FIXED here, on the server. The page shows them as
checkboxes, and ExportCandidatesForm accepts only these keys — so editing the
page in devtools to ask for, say, a password hash gets a form error, not a
column. Locked columns (email; email and exam) are always written and are not
choices at all.

Every list is in priority order, which is also the order in the file — the
order the boxes were ticked does not matter.

All dates and times are Asia/Kolkata (IST), whatever the candidate's own
zone: admins are all in India, and one zone across the file is what they
reason in. The candidate's own zone is available as its own column.
"""

import csv
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.exam.timezones import DEFAULT_TIMEZONE, to_local

#: The zone every date and time in an export is written in.
EXPORT_TIMEZONE = DEFAULT_TIMEZONE  # "Asia/Kolkata"

#: Written for a value that does not exist — no phone, not graded, not
#: cancelled. Never escaped (see _safe), so it stays a plain dash in Excel.
MISSING = "-"


def _ist(moment):
    """A stored (UTC) instant as "YYYY-MM-DD HH:MM" in IST — sorts correctly in Excel."""
    return to_local(moment, EXPORT_TIMEZONE).strftime("%Y-%m-%d %H:%M") if moment else None


def today_ist():
    """Today's date in IST — for the filename, so a 2 AM export is not dated yesterday."""
    return timezone.localdate(timezone=ZoneInfo(EXPORT_TIMEZONE))


def _person(user):
    """How a user who acted on a booking (booked, cancelled, graded) is named."""
    return (user.display_name or user.email) if user else None


def _booking_status(b):
    """
    The status as an admin would describe it — the same words as the
    candidate detail page. A booking stays "booked" in the database until
    something changes it, so an open one is described by its stage instead:
    an exam that finished last week reads "Missed", not "Booked".
    """
    stage = b.stage
    if stage == "upcoming":
        return "Upcoming"
    if stage == "underway":
        return "Underway"
    if stage == "lapsed":
        return "Missed"
    return b.get_status_display()


# key -> (header, how to read it from the row's object)

#: One row per candidate. The row is a User, annotated with `export_bookings`
#: (see apps.home.views.export_candidates).
CANDIDATE_LOCKED = {"email": ("Email", lambda u: u.email)}
CANDIDATE_COLUMNS = {
    "name": ("Name", lambda u: u.display_name),
    "login_id": ("Login id", lambda u: u.external_id),
    "phone": ("Phone", lambda u: u.contact_number),
    "linkedin": ("LinkedIn", lambda u: u.linkedin_link),
    "github_link": ("GitHub link", lambda u: u.github_link),
    "github_username": ("GitHub username", lambda u: u.github_username),
    "joined": ("Joined (IST)", lambda u: _ist(u.created_at)),
    # Counts only the bookings that match the filters, so the column agrees
    # with what was asked for: "Selenium in October" counts those.
    "bookings": ("Bookings", lambda u: u.export_bookings),
}

#: One row per booking. The row is an ExamBooking with candidate, exam and the
#: three acting users selected.
BOOKING_LOCKED = {
    "email": ("Email", lambda b: b.candidate.email),
    "exam": ("Exam", lambda b: b.exam.exam_name),
}
BOOKING_COLUMNS = {
    "name": ("Name", lambda b: b.candidate.display_name),
    "login_id": ("Login id", lambda b: b.candidate.external_id),
    "phone": ("Phone", lambda b: b.candidate.contact_number),
    "round": ("Round", lambda b: b.get_round_type_display()),
    "ref": ("Booking ref", lambda b: str(b.booking_id)[:8]),
    "exam_at": ("Exam date & time (IST)", lambda b: _ist(b.scheduled_at)),
    "candidate_timezone": ("Candidate's timezone", lambda b: b.booked_timezone),
    "status": ("Status", _booking_status),
    "marks": ("Marks", lambda b: b.marks_obtained),
    "maximum_marks": ("Maximum marks", lambda b: b.maximum_marks),
    "booked_by": ("Booked by", lambda b: _person(b.booked_by)),
    "cancelled_by": ("Cancelled by", lambda b: _person(b.cancelled_by)),
    "cancellation_reason": ("Cancellation reason", lambda b: b.cancellation_reason),
    "graded_by": ("Graded by", lambda b: _person(b.graded_by)),
    "graded_at": ("Graded at (IST)", lambda b: _ist(b.graded_at)),
}

EXPORTS = {
    "candidates": (CANDIDATE_LOCKED, CANDIDATE_COLUMNS),
    "bookings": (BOOKING_LOCKED, BOOKING_COLUMNS),
}


def ist_day_bounds(date_from, date_to):
    """
    The From/To dates as a UTC half-open range [start, end) for
    scheduled_at, read as IST calendar days. To is included, so 1–31 Oct
    ends at the start of 1 Nov. No To means From's day alone.
    """
    last = date_to or date_from
    zone = ZoneInfo(EXPORT_TIMEZONE)
    start = timezone.make_aware(datetime.combine(date_from, datetime.min.time()), zone)
    end = timezone.make_aware(datetime.combine(last + timedelta(days=1), datetime.min.time()), zone)
    return start, end


def _safe(value):
    """
    One cell's text, safe to open in Excel.

    CSV injection: Excel runs a cell starting with = + - or @ as a formula,
    and a candidate chooses their own name and links. A leading apostrophe
    makes Excel treat it as text. Plain numbers like a phone "+91 98765 43210"
    are left alone — digits, spaces and + - ( ) cannot call anything — so
    phones do not come out with a stray apostrophe.
    """
    if value is None or value == "":
        return MISSING
    text = str(value)
    if text[0] in "=@\t\r":
        return "'" + text
    if text[0] in "+-" and not all(c in "0123456789 +-()." for c in text):
        return "'" + text
    return text


class _Echo:
    """A file-like object csv.writer can write to, which hands back each line."""

    def write(self, value):
        return value


def csv_rows(kind, chosen, rows):
    """
    The CSV, one line at a time, for a StreamingHttpResponse — so a large
    export is never held in memory whole.

    `chosen` is the optional column keys from the form; they are written in
    the list's own order, after the locked columns.
    """
    locked, optional = EXPORTS[kind]
    columns = list(locked.values()) + [col for key, col in optional.items() if key in chosen]
    writer = csv.writer(_Echo())
    # A UTF-8 byte-order mark first, or Excel reads the file as the wrong
    # encoding and "José" comes out garbled.
    yield "﻿" + writer.writerow([header for header, _ in columns])
    for row in rows:
        yield writer.writerow([_safe(read(row)) for _, read in columns])
