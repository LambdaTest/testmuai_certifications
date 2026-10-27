"""
Email for the exam domain. Views import one thing from here:

    from .emails import queue_email
    queue_email("booking_confirmed", booking, actor=request.user)

which records the email (OutboundEmail) and sends it right after the view's
transaction commits. Everything else — which mailer, which templates, the
calendar invite, retries, skipping what is stale — happens behind it:

    registry.py   what each email is
    context.py    what its templates receive
    sender.py     the only code that talks to the mail server
    jobs.py       the email steps of manage.py run_scheduled_jobs
"""

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.exam.models import OutboundEmail

from .registry import EVENTS
from .sender import send_after_commit

log = logging.getLogger(__name__)


def _recipient(booking, actor):
    """
    Who receives it: the candidate. On the demo (EMAIL_SEND_TO_ACTOR) the
    person whose action caused it — and for the scheduled job's emails, which
    nobody's click caused, whoever made the booking.
    """
    if settings.EMAIL_SEND_TO_ACTOR:
        person = actor or booking.booked_by or booking.candidate
    else:
        person = booking.candidate
    return (person.email or "").strip() if person else ""


def queue_email(event, booking, *, actor=None, send_after=None):
    """
    Queues one email about `booking` and returns its OutboundEmail row — or
    None when there is no one to send it to (an anonymous booking, a user
    with no email).

    Safe to call more than once for the same email: the dedupe key makes the
    second call return the existing row instead of a duplicate. That is what
    lets the scheduled job ask "remind this booking?" every minute.

    send_after delays it ("booking expired" goes hours after it is queued);
    otherwise it is sent as soon as the current transaction commits — never
    for a change that rolled back.
    """
    spec = EVENTS[event]
    recipient = _recipient(booking, actor)
    if not recipient:
        log.info("No email address for %s on booking %s; not queued.", event, booking.booking_id)
        return None

    due = send_after or timezone.now()
    row, created = OutboundEmail.objects.get_or_create(
        dedupe_key=spec.key(booking),
        defaults={
            "event": event,
            "mailer": spec.mailer,
            "booking": booking,
            "recipient": recipient,
            "scheduled_for": booking.scheduled_at,
            "next_attempt_at": due,
        },
    )
    if created and due <= timezone.now():
        transaction.on_commit(lambda: send_after_commit(row.pk))
    return row
