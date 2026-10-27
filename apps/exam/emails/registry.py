"""
What each email is: its mailer, its templates, its dedupe key, whether it
carries a calendar invite, and when it has stopped being worth sending.

Adding an email is one entry here plus a folder of templates under
templates/emails/<template>/ (subject.txt, body.txt, body.html). Nothing else
needs to know about it — views call queue_email("<key>", booking).
"""

from dataclasses import dataclass
from typing import Callable, Optional

from apps.exam.models import ExamBooking

S = ExamBooking.Status


def _iso(moment):
    return moment.isoformat() if moment else ""


@dataclass(frozen=True)
class EmailEvent:
    #: A key of settings.MAILERS — the sender name and subject prefix.
    mailer: str
    #: The folder under templates/emails/.
    template: str
    #: The dedupe key for a booking: what makes this email *this* email, so it
    #: can never be queued twice (OutboundEmail.dedupe_key is unique).
    key: Callable[[ExamBooking], str]
    #: Why it should no longer be sent, or None if it still should. Asked
    #: just before every attempt — a retry can come long after the queueing,
    #: and a stale email is worse than none.
    skip_reason: Callable[["OutboundEmail", ExamBooking, object], Optional[str]]
    #: None, "event" (the booking's invite) or "cancel" (removes it).
    calendar: Optional[str] = None


# ---- skip rules ----------------------------------------------------------

def _still_booked(row, b, now):
    if b.status != S.BOOKED:
        return f"booking is now {b.get_status_display().lower()}"
    return None


def _still_booked_at_that_time(row, b, now):
    reason = _still_booked(row, b, now)
    if reason:
        return reason
    if row.scheduled_for and b.scheduled_at != row.scheduled_for:
        return "booking has been rescheduled since"
    return None


def _instant_still_joinable(row, b, now):
    # Begun already is fine — the email is still the record of the booking.
    # Only once joining has closed would "you can rejoin until…" be untrue.
    if b.status not in (S.BOOKED, S.ATTENDED):
        return f"booking is now {b.get_status_display().lower()}"
    if now >= b.join_closes_at:
        return "the join window has closed"
    return None


def _still_cancelled(row, b, now):
    return None if b.status == S.CANCELLED else f"booking is now {b.get_status_display().lower()}"


def _reminder_still_useful(row, b, now):
    reason = _still_booked_at_that_time(row, b, now)
    if reason:
        return reason
    # Never late: a reminder that arrives after the start (a retry, or the
    # job catching up) only confuses.
    if now >= b.scheduled_at:
        return "the exam has already started"
    return None


def _second_round_still_open(row, b, now):
    reason = _still_booked(row, b, now)
    if reason:
        return reason
    if now >= b.join_closes_at:
        return "the second round's window has closed"
    return None


def _still_missed(row, b, now):
    return None if b.status == S.NO_SHOW else f"booking is now {b.get_status_display().lower()}"


# ---- the events ----------------------------------------------------------

EVENTS = {
    # The candidate booked on /book.
    "booking_confirmed": EmailEvent(
        mailer="exam", template="booking_confirmed",
        key=lambda b: f"booking_confirmed:{b.booking_id}",
        skip_reason=_still_booked, calendar="event",
    ),
    # Start Instant Exam: booked for now, and the candidate is on the T&C
    # page already. No calendar invite — it is happening now — and no
    # reschedule or cancel, which closed before it was booked.
    "instant_booking": EmailEvent(
        mailer="exam", template="instant_booking",
        key=lambda b: f"instant_booking:{b.booking_id}",
        skip_reason=_instant_still_joinable,
    ),
    # An admin booked on the candidate's behalf (Candidate Center → Book Exam).
    "booked_by_admin": EmailEvent(
        mailer="exam", template="booked_by_admin",
        key=lambda b: f"booked_by_admin:{b.booking_id}",
        skip_reason=_still_booked, calendar="event",
    ),
    # One per reschedule: the new time and the calendar sequence are in the
    # key, so moving it twice — even back to the first time — emails twice.
    "booking_rescheduled": EmailEvent(
        mailer="exam", template="booking_rescheduled",
        key=lambda b: f"booking_rescheduled:{b.booking_id}:{_iso(b.scheduled_at)}:{b.calendar_sequence}",
        skip_reason=_still_booked_at_that_time, calendar="event",
    ),
    "booking_cancelled": EmailEvent(
        mailer="exam", template="booking_cancelled",
        key=lambda b: f"booking_cancelled:{b.booking_id}",
        skip_reason=_still_cancelled, calendar="cancel",
    ),
    # No reason in it — the admin's reason stays internal.
    "booking_cancelled_by_admin": EmailEvent(
        mailer="exam", template="booking_cancelled_by_admin",
        key=lambda b: f"booking_cancelled_by_admin:{b.booking_id}",
        skip_reason=_still_cancelled, calendar="cancel",
    ),
    # Reminders carry the scheduled time in the key, so a rescheduled booking
    # gets reminders for its new time. Never for a two-round exam's second
    # round — "second round open" covers it (see jobs.queue_due_reminders).
    "reminder_60": EmailEvent(
        mailer="reminders", template="reminder",
        key=lambda b: f"reminder_60:{b.booking_id}:{_iso(b.scheduled_at)}",
        skip_reason=_reminder_still_useful,
    ),
    "reminder_30": EmailEvent(
        mailer="reminders", template="reminder",
        key=lambda b: f"reminder_30:{b.booking_id}:{_iso(b.scheduled_at)}",
        skip_reason=_reminder_still_useful,
    ),
    # The objective round of a two-round exam was submitted; the subjective
    # round (the booking passed in) is open for 36 hours.
    "second_round_open": EmailEvent(
        mailer="exam", template="second_round_open",
        key=lambda b: f"second_round_open:{b.booking_id}",
        skip_reason=_second_round_still_open,
    ),
    # Never joined: queued by the scheduled job when the window closes, to go
    # settings.EMAIL_EXPIRED_DELAY_HOURS later. For a missed second round the
    # whole exam was cancelled, and the template says so.
    "booking_expired": EmailEvent(
        mailer="exam", template="booking_expired",
        key=lambda b: f"booking_expired:{b.booking_id}",
        skip_reason=_still_missed,
    ),
}
