"""
One-off data update for the status rules agreed on 27 Oct.

Until now a submitted objective round stayed `attended` forever, and the
one-open-booking rule counts `attended` — so a candidate could never book
that exam again. From now on:

  - an objective-only exam is `graded` the moment it is submitted;
  - a two-round exam's first round becomes `graded` when its second round is
    graded (or `cancelled` by the scheduled job if the second round is missed).

This brings existing rows into line with those rules. Nothing is deleted;
only `status` changes, and only on the rows described. Bookings still in
progress (a second round still open) are left alone — the new code moves
them on when the time comes.

Not reversible in any useful sense: after it runs there is no record of which
rows it moved. Reversing it does nothing.
"""

from django.db import migrations


def release(apps, schema_editor):
    ExamBooking = apps.get_model("exam", "ExamBooking")

    # Objective-only exams, submitted.
    ExamBooking.objects.filter(
        round_type="objective",
        status="attended",
        sheet__submitted_at__isnull=False,
    ).exclude(exam__exam_type="both").update(status="graded")

    # Two-round exams whose second round has been graded.
    ExamBooking.objects.filter(
        round_type="objective",
        exam__exam_type="both",
        status="attended",
        subjective_booking__status="graded",
    ).update(status="graded")


class Migration(migrations.Migration):

    dependencies = [
        ("exam", "0019_outbound_email_and_calendar_sequence"),
    ]

    operations = [
        migrations.RunPython(release, migrations.RunPython.noop),
    ]
