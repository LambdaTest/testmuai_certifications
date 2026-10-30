"""
Finishing a paper — what happens once it has been submitted, however that
happened: the candidate pressed Submit (views.submit_exam) or their time ran
out and the scheduled job closed it (sweeps.close_abandoned_papers).

One copy, so a paper ends the same way on either path. Plain functions, no
request, per the project rule that business logic does not need HTTP.
"""

from datetime import timedelta

from .emails import queue_email
from .models import Exam, ExamBooking, ExamSheetQuestion


def grade_exam(booking, sheet):
    """
    Grades the exam after submission.
    """
    if booking.round_type == Exam.Type.OBJECTIVE:
        # Grade the exam only if it's an objective exam.
        marks_obtained = 0
        maximum_marks = 0
        questions = ExamSheetQuestion.objects.filter(sheet=sheet).select_related("question", "selected_option")
        for question in questions:
            # What this paper was out of — the marks of the questions actually
            # served, not the exam's settings, which can change afterwards.
            maximum_marks += question.marks
            if question and question.selected_option and question.selected_option.is_correct:
                question.marks_awarded = question.marks
                marks_obtained += question.marks
            else:
                question.marks_awarded = 0
            question.save()
        booking.marks_obtained = marks_obtained
        booking.maximum_marks = maximum_marks
        booking.save()
        return marks_obtained
    elif booking.round_type == Exam.Type.SUBJECTIVE:
        # Subjective exams are graded manually
        pass


def finish_submitted_paper(booking, sheet, actor=None):
    """
    Moves a booking on once its paper is stamped submitted (sheet.submitted_at
    set). Call inside the transaction that stamped it. Returns True when it
    opened a second round.

      subjective round            -> under_review, the examiner's queue
      objective round             -> graded automatically (grade_exam)
        objective-only exam       -> graded, pass mark frozen: the exam is over
        first of a two-round exam -> stays attended, holding the exam, and the
                                     subjective round is booked 30 minutes
                                     after the submit, with its own email

    `actor` is who caused it, for the demo's EMAIL_SEND_TO_ACTOR — the
    candidate on Submit, nobody when the job closes it.
    """
    if booking.round_type == Exam.Type.SUBJECTIVE:
        booking.status = ExamBooking.Status.UNDER_REVIEW
        booking.save(update_fields=["status", "updated_at"])

    grade_exam(booking, sheet)

    if booking.round_type == Exam.Type.OBJECTIVE and booking.exam.exam_type != Exam.Type.BOTH:
        booking.status = ExamBooking.Status.GRADED
        booking.save(update_fields=["status", "updated_at"])
        booking.freeze_passing_marks()

    is_first_of_two = (
        booking.exam.exam_type == Exam.Type.BOTH
        and booking.round_type == Exam.Type.OBJECTIVE
    )
    if is_first_of_two:
        second_round = ExamBooking.objects.create(
            candidate=booking.candidate,
            exam=booking.exam,
            round_type=Exam.Type.SUBJECTIVE,
            status=ExamBooking.Status.BOOKED,
            parent_booking=booking,
            booked_timezone=booking.booked_timezone,
            scheduled_at=sheet.submitted_at + timedelta(minutes=Exam.ROUND_GAP_MINUTES),
        )
        queue_email("second_round_open", second_round, actor=actor)
    return is_first_of_two
