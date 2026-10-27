"""
Everything that happens because time passes, rather than because someone
clicked. Run it every minute:

    AWS / any server     cron:  * * * * *  python manage.py run_scheduled_jobs
    PythonAnywhere       an always-on task: python manage.py run_scheduled_jobs --loop
    By hand, locally     python manage.py run_scheduled_jobs

Each step is safe to repeat and isolated from the others: one failing is
logged and reported, and the rest still run — a bug in one must never stop
reminders going out.

Run it on one server. Two at once would not send anything twice (rows and
bookings are claimed under locks), but there is no reason for it.
"""

import logging
import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.exam.emails.jobs import cleanup, queue_due_reminders, send_due_emails
from apps.exam.sweeps import mark_missed_bookings

log = logging.getLogger(__name__)

#: In order. Missed bookings first, so the "booking expired" emails they
#: queue are seen by the send step of the same run once due.
STEPS = [
    ("queue reminders", queue_due_reminders),
    ("mark missed bookings", mark_missed_bookings),
    ("send due emails", send_due_emails),
    ("clean up old emails", cleanup),
]


class Command(BaseCommand):
    help = "Reminders, missed bookings, sending and retrying email, cleanup. Run every minute."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true",
                            help="Keep running, once every --interval seconds (for an always-on task).")
        parser.add_argument("--interval", type=int, default=60)

    def handle(self, *args, loop=False, interval=60, **options):
        while True:
            self.run_once()
            if not loop:
                return
            time.sleep(interval)

    def run_once(self):
        now = timezone.now()
        for name, step in STEPS:
            try:
                result = step(now)
            except Exception:
                log.exception("Scheduled step %r failed", name)
                self.stderr.write(f"{now:%Y-%m-%d %H:%M:%S} {name}: FAILED (see log)")
            else:
                if result:
                    self.stdout.write(f"{now:%Y-%m-%d %H:%M:%S} {name}: {result}")
