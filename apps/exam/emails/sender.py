"""
Sends one queued email. The only code that talks to the mail server.

Both paths end here: the immediate send just after a view's transaction
commits, and the scheduled job's retries. So an email looks and behaves the
same whichever path sent it.

Every attempt writes its outcome back to the OutboundEmail row:

  sent      done
  pending   failed, will be retried at next_attempt_at (1, 5, 15, 30 minutes)
  failed    given up — out of attempts, or the address was refused
  skipped   no longer worth sending (a reminder for a cancelled booking…)
"""

import logging
from datetime import timedelta
from email.utils import formataddr
from smtplib import SMTPRecipientsRefused

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.exam.calendar import build_ics
from apps.exam.models import ExamBooking, OutboundEmail

from .context import build_context
from .registry import EVENTS

log = logging.getLogger(__name__)
Status = OutboundEmail.Status


def send_pending(row_id):
    """
    Attempts one pending email, if it is due and nobody else has it.

    The row is locked for the attempt with skip_locked: if the scheduled job
    and the immediate send reach the same row at once, one sends and the
    other moves on — an email is never sent twice.
    """
    now = timezone.now()
    with transaction.atomic():
        row = (
            OutboundEmail.objects.select_for_update(skip_locked=True)
            .filter(pk=row_id, status=Status.PENDING, next_attempt_at__lte=now)
            .first()
        )
        if row is None:
            return None
        _attempt(row, now)
        return row


def send_after_commit(row_id):
    """
    The immediate send, run by transaction.on_commit once the view's changes
    are saved. Never raises: the booking is already saved, and a mail
    problem must not turn the candidate's page into an error. Anything not
    sent here is retried by the scheduled job.
    """
    try:
        send_pending(row_id)
    except Exception:
        log.exception("Immediate send of email %s failed; the scheduled job will retry it.", row_id)


def _attempt(row, now):
    booking = (
        ExamBooking.objects.select_related("exam__subject", "candidate")
        .filter(pk=row.booking_id).first()
    )
    event = EVENTS.get(row.event)
    if booking is None or event is None:
        return _finish(row, Status.SKIPPED, "booking or email type no longer exists")

    reason = event.skip_reason(row, booking, now)
    if reason:
        return _finish(row, Status.SKIPPED, reason)

    row.attempts += 1
    try:
        _build_message(row, event, booking, now).send()
    except SMTPRecipientsRefused as exc:
        # The address itself was refused — retrying cannot help.
        _finish(row, Status.FAILED, f"recipient refused: {exc}")
    except Exception as exc:
        # The server was down, timed out, refused the login — or a bug in a
        # template. All worth retrying: the first two pass, the last gets
        # fixed, and the retries pick the email up again either way.
        log.warning("Email %s (%s) attempt %s failed: %s", row.pk, row.event, row.attempts, exc)
        delays = settings.EMAIL_RETRY_DELAYS_MINUTES
        if row.attempts >= settings.EMAIL_MAX_ATTEMPTS:
            _finish(row, Status.FAILED, f"gave up after {row.attempts} attempts: {exc}")
        else:
            row.next_attempt_at = now + timedelta(minutes=delays[min(row.attempts, len(delays)) - 1])
            _finish(row, Status.PENDING, str(exc))
    else:
        row.sent_at = now
        _finish(row, Status.SENT, "")


def _finish(row, status, detail):
    row.status = status
    row.detail = (detail or "")[:500]
    row.save(update_fields=["status", "detail", "attempts", "next_attempt_at", "sent_at"])


def _build_message(row, event, booking, now):
    mailer = settings.MAILERS[event.mailer]
    context = build_context(row, booking, now)
    folder = f"emails/{event.template}"

    # A subject is one line, whatever the template's whitespace.
    subject = " ".join(render_to_string(f"{folder}/subject.txt", context).split())
    subject = f"{mailer['subject_prefix']}: {subject}"
    # On the demo the email goes to whoever acted, not the candidate; say
    # whose email it really is, so a reviewer reading an admin's inbox can tell.
    candidate_email = booking.candidate.email if booking.candidate else ""
    if candidate_email and row.recipient.lower() != candidate_email.lower():
        subject = f"[for {candidate_email}] {subject}"

    message = EmailMultiAlternatives(
        subject=subject,
        body=render_to_string(f"{folder}/body.txt", context),
        from_email=formataddr((mailer["display_name"], settings.DEFAULT_FROM_EMAIL)),
        to=[row.recipient],
        reply_to=[settings.EMAIL_REPLY_TO],
        headers={
            # For tracing and filtering — which kind of email, which event,
            # which booking — without opening it.
            "X-Mailer-Type": event.mailer,
            "X-Email-Event": row.event,
            "X-Booking-Ref": context["ref"],
        },
    )
    message.attach_alternative(render_to_string(f"{folder}/body.html", context), "text/html")

    if event.calendar:
        # The same UID as the .ics download, with the booking's current
        # sequence: the candidate's calendar moves or removes the event it
        # already has rather than adding a second one.
        message.attach(
            f"exam-{context['ref']}.ics",
            build_ics(
                booking,
                sequence=booking.calendar_sequence,
                cancelled=event.calendar == "cancel",
                url=context["booking_url"],
            ),
            "text/calendar",
        )
    return message
