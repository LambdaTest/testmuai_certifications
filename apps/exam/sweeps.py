"""
Booking housekeeping for manage.py run_scheduled_jobs — the changes nobody's
click makes, because they are about time passing.

Kept beside the bookings rather than in apps.exam.emails: these change
bookings; the emails they queue are a consequence.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q

from .emails import queue_email
from .models import Exam, ExamBooking

#: The reason written on round one of a two-round exam whose second round was
#: never attempted. The exam is one exam in two parts: missing part two
#: cancels it, with no pass or fail. Admins see this on the candidate's page.
SECOND_ROUND_MISSED_REASON = "Cancellation due to no attempt on 2nd round"

#: How stale an expiry can be and still be emailed. The first run on an old
#: database finds bookings missed weeks ago; their status is corrected, but
#: "your booking expired" about an exam from last month would only confuse.
EXPIRED_EMAIL_MAX_AGE = timedelta(hours=24)


def mark_missed_bookings(now):
    """
    Marks bookings nobody began as no_show once their join window has closed
    (start + 45 minutes for an objective round, + 36 hours for a subjective
    one), and queues "booking expired" for EMAIL_EXPIRED_DELAY_HOURS later.

    That status change is what lets the candidate book the exam again: the
    one-open-booking rule counts booked rows, and a missed booking used to
    stay booked forever.

    For the second round of a two-round exam the whole exam is over: round
    one, still attended, is cancelled by the system (cancelled_by empty) with
    SECOND_ROUND_MISSED_REASON — which also releases it for a new booking.
    """
    lapsed = Q()
    for round_type, minutes in Exam.DURATION_BY_TYPE.items():
        lapsed |= Q(round_type=round_type, scheduled_at__lte=now - timedelta(minutes=minutes))
    pks = list(
        ExamBooking.objects.filter(lapsed, status=ExamBooking.Status.BOOKED).values_list("pk", flat=True)
    )

    marked = 0
    for pk in pks:
        with transaction.atomic():
            # Locked and re-checked: the candidate may be pressing "I'm ready
            # to begin" at this very moment, and that must win or lose cleanly.
            booking = (
                ExamBooking.objects.select_for_update(skip_locked=True)
                .filter(pk=pk, status=ExamBooking.Status.BOOKED).first()
            )
            if booking is None or now < booking.join_closes_at:
                continue
            booking.status = ExamBooking.Status.NO_SHOW
            booking.save(update_fields=["status", "updated_at"])
            marked += 1

            if booking.parent_booking_id:
                first_round = ExamBooking.objects.select_for_update().get(pk=booking.parent_booking_id)
                if first_round.status == ExamBooking.Status.ATTENDED:
                    first_round.status = ExamBooking.Status.CANCELLED
                    first_round.cancellation_reason = SECOND_ROUND_MISSED_REASON
                    first_round.cancelled_at = now
                    first_round.cancelled_by = None  # the system, not an admin
                    first_round.save(update_fields=[
                        "status", "cancellation_reason", "cancelled_at", "cancelled_by", "updated_at",
                    ])

            send_at = booking.join_closes_at + timedelta(hours=settings.EMAIL_EXPIRED_DELAY_HOURS)
            if send_at >= now - EXPIRED_EMAIL_MAX_AGE:
                queue_email("booking_expired", booking, send_after=send_at)
    return marked
