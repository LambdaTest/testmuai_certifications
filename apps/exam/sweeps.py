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


#: Written on a subjective round that ran out of time with nothing submitted.
SUBJECTIVE_NOT_SUBMITTED_REASON = "Not submitted within the 36-hour window"


def close_abandoned_papers(now):
    """
    Closes papers begun but never submitted once their time is up
    (ExamSheet.expires_at: the moment they began + 45 minutes objective,
    36 hours subjective). The candidate pressed "I'm ready to begin" and left.

    OBJECTIVE ROUND — submitted as a timeout at its deadline and graded on
    whatever autosave stored, exactly as if time had run out with the page
    open: finish_submitted_paper, the same code the Submit button runs. An
    objective-only exam is then graded; the first round of a two-round exam
    opens the second round as usual (with its own email). The candidate is
    told their time ran out and the paper was submitted and graded.

    SUBJECTIVE ROUND — there is no answer to grade: it only exists when they
    submit. The round is cancelled by the system (cancelled_by empty) with
    SUBJECTIVE_NOT_SUBMITTED_REASON, and on a two-round exam round one is
    cancelled too, as for a missed second round — which also lets the
    candidate book the exam again. They are told the exam was cancelled.

    The sheet is stamped submitted_at = expires_at, TIMEDOUT, either way, so
    it is closed exactly once. Old papers found on a first run are closed but
    not emailed (EXPIRED_EMAIL_MAX_AGE).
    """
    from .models import ExamSheet
    from .papers import finish_submitted_paper

    pks = list(
        ExamSheet.objects.filter(
            submitted_at__isnull=True,
            expires_at__lte=now,
            booking__status=ExamBooking.Status.ATTENDED,
        ).values_list("pk", flat=True)
    )

    closed = 0
    for pk in pks:
        with transaction.atomic():
            # Locked and re-checked: the candidate's own late Submit may be
            # arriving at this moment, and only one of them may close it.
            sheet = (
                ExamSheet.objects.select_for_update(skip_locked=True)
                .filter(pk=pk, submitted_at__isnull=True).first()
            )
            if sheet is None:
                continue
            booking = (
                ExamBooking.objects.select_for_update().select_related("exam")
                .get(pk=sheet.booking_id)
            )
            if booking.status != ExamBooking.Status.ATTENDED or now < sheet.expires_at:
                continue

            sheet.submitted_at = sheet.expires_at
            sheet.submission_status = ExamSheet.SubmissionStatus.TIMEDOUT
            sheet.save(update_fields=["submitted_at", "submission_status"])
            recent = sheet.expires_at >= now - EXPIRED_EMAIL_MAX_AGE

            if booking.round_type == Exam.Type.OBJECTIVE:
                finish_submitted_paper(booking, sheet)
                if recent:
                    queue_email("objective_timed_out", booking)
            else:
                booking.status = ExamBooking.Status.CANCELLED
                booking.cancellation_reason = SUBJECTIVE_NOT_SUBMITTED_REASON
                booking.cancelled_at = now
                booking.cancelled_by = None  # the system, not an admin
                booking.save(update_fields=[
                    "status", "cancellation_reason", "cancelled_at", "cancelled_by", "updated_at",
                ])
                if booking.parent_booking_id:
                    first_round = ExamBooking.objects.select_for_update().get(pk=booking.parent_booking_id)
                    if first_round.status == ExamBooking.Status.ATTENDED:
                        first_round.status = ExamBooking.Status.CANCELLED
                        first_round.cancellation_reason = SECOND_ROUND_MISSED_REASON
                        first_round.cancelled_at = now
                        first_round.cancelled_by = None
                        first_round.save(update_fields=[
                            "status", "cancellation_reason", "cancelled_at", "cancelled_by", "updated_at",
                        ])
                if recent:
                    queue_email("subjective_timed_out", booking)
            closed += 1
    return closed
