"""
The email steps of manage.py run_scheduled_jobs. Each is safe to run every
minute, and to run again after a crash: queueing is deduplicated by the
dedupe key, and sending claims each row under a lock.
"""

from datetime import timedelta

from django.conf import settings

from apps.exam.models import ExamBooking, OutboundEmail

from . import queue_email
from .sender import send_pending


def queue_due_reminders(now):
    """
    Queues the 60- and 30-minute reminders for bookings coming up.

    Each reminder has its own slot and is sent only inside it: the 60-minute
    one from 60 to 30 minutes before, the 30-minute one from 30 minutes to
    the start. So a job that was down and catches up at 20 minutes to go
    sends "starts in 30 minutes" — not "in 60" — and nothing after the start.

    Not for the second round of a two-round exam: it opens 30 minutes after
    round one is submitted, and the "second round open" email covers it.
    """
    marks = sorted(settings.EMAIL_REMINDER_MINUTES, reverse=True)  # [60, 30]
    queued = 0
    for i, minutes in enumerate(marks):
        until = marks[i + 1] if i + 1 < len(marks) else 0
        due = (
            ExamBooking.objects.filter(
                status=ExamBooking.Status.BOOKED,
                parent_booking__isnull=True,
                candidate__isnull=False,
                scheduled_at__gt=now + timedelta(minutes=until),
                scheduled_at__lte=now + timedelta(minutes=minutes),
            )
            .select_related("candidate", "booked_by", "exam")
        )
        for booking in due:
            if queue_email(f"reminder_{minutes}", booking):
                queued += 1
    return queued


def send_due_emails(now, limit=200):
    """
    Sends every pending email whose time has come — retries, and anything
    queued for later such as "booking expired". One at a time, each under its
    own lock, so a run that overlaps another never sends the same email twice.
    """
    ids = list(
        OutboundEmail.objects.filter(status=OutboundEmail.Status.PENDING, next_attempt_at__lte=now)
        .order_by("next_attempt_at")
        .values_list("pk", flat=True)[:limit]
    )
    sent = 0
    for pk in ids:
        row = send_pending(pk)
        if row is not None and row.status == OutboundEmail.Status.SENT:
            sent += 1
    return sent


def cleanup(now):
    """
    Deletes sent and skipped emails older than EMAIL_RETENTION_DAYS, so the
    table holds a rolling few months rather than growing forever. Failed ones
    stay, for whoever looks into "I never got my email".
    """
    deleted, _ = OutboundEmail.objects.filter(
        status__in=[OutboundEmail.Status.SENT, OutboundEmail.Status.SKIPPED],
        created_at__lt=now - timedelta(days=settings.EMAIL_RETENTION_DAYS),
    ).delete()
    return deleted
