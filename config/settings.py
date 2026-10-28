"""
Django settings for the TestMu AI Certifications platform.
"""

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes"}


# Off unless asked for. Development turns it on in .env (DJANGO_DEBUG=True);
# a server started without its environment must not show error pages full of
# code and settings to the public.
DEBUG = env_bool("DJANGO_DEBUG", False)

# The dev key only while DEBUG is on. With DEBUG off a missing key stops the
# server from starting, rather than running with a key that is public — in
# this repo — and lets anyone forge a login session.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set when DEBUG is off. For local "
            "development, copy .env.example to .env (it sets DJANGO_DEBUG=True)."
        )
    SECRET_KEY = "dev-only-change-me"
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.home",
    "apps.exam",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Postgres everywhere, including local development.
#
# No SQLite fallback on purpose. SQLite differs on JSONB (question payloads and
# answer keys), timestamptz, constraint enforcement, and concurrency — a silent
# fallback means code that passes locally can behave differently in production.
# If this connection fails, start Postgres; don't work around it.
DATABASES = {
    "default": dj_database_url.config(
        default="postgres://postgres:postgres@localhost:5432/testmuai_certifications",
        conn_max_age=600,
    )
}

# Must be set before the first migration. Changing it afterwards means starting
# the migration history over — see apps/home/models.py.
AUTH_USER_MODEL = "home.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "en-us"

# Everything is stored in UTC and converted for display. Candidate-facing times
# are rendered in the timezone they booked in, never the server's.
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Uploaded media ----------------------------------------------------------
# Author-uploaded question and answer media. Distinct from STATIC: static files
# ship with the code, media arrives at runtime and must survive a deploy.
#
# Local disk is fine for development. It is NOT fine for the deployment target —
# an EC2 instance that gets replaced loses every upload, and more than one
# instance means each has a different idea of what exists. Before this goes
# live, MEDIA_ROOT becomes S3 via a storage backend, and MEDIA_URL its bucket.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Booking rules -----------------------------------------------------------
# Enforced in forms and models, not only in the UI.
#
# Changed here, by a developer, on request — deliberately no admin page for
# them (decided 12 Oct). They change rarely, and editing a number here is a far
# smaller job than building and securing a settings screen.
BOOKING_MIN_DAYS_AHEAD = 1  # no same-day booking
BOOKING_MAX_MONTHS_AHEAD = 3
#: Clear time required between the end of one exam and the start of the
#: next, so a candidate is never double-booked or rushed between sittings.
BOOKING_GAP_MINUTES = 60
#: Reschedule and cancel close this long before the scheduled start. By then
#: the candidate should be getting ready, not moving the slot — and since a
#: paper can only be begun from the start time, closing before it also means a
#: started paper can never be rescheduled or cancelled out from under itself.
BOOKING_CHANGE_CUTOFF_MINUTES = 10
#: Admins can cancel a booking until this long before the start — later than
#: candidates, for the emergency a candidate reports at the last minute.
#: Still before the start, so a paper can never be cancelled once begun.
ADMIN_CANCEL_CUTOFF_MINUTES = 5

#: How long a certificate is valid. Copied onto each certificate as
#: expires_at when it is issued, so changing this affects only certificates
#: issued afterwards.
CERTIFICATE_VALIDITY_YEARS = 2

# --- Email ------------------------------------------------------------------
#
# Sent over SMTP, through apps.exam.emails — never from a view directly. Where
# it goes is only these settings: locally Mailpit (docker compose, inbox at
# http://localhost:8025), in production Gmail. The code is the same for both.

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "1025"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
#: Seconds to wait on the mail server. Without it a hung server hangs the
#: request that sent the email; with it the send fails and is retried.
EMAIL_TIMEOUT = 10

#: The one sending address. Every mailer sends from it; they differ only in
#: display name and subject prefix.
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "certifications@testmuai.com")
#: Where replies go — the same company address, so a candidate can reply with
#: a question. Never a no-reply address.
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO", DEFAULT_FROM_EMAIL)

#: The site's own address, for links in emails. Emails need absolute links
#: (https://…/assessment/…); a page's relative links mean nothing in an inbox.
SITE_URL = os.environ.get("SITE_URL", "http://127.0.0.1:8000").rstrip("/")

#: Mailers: one per kind of email, all from DEFAULT_FROM_EMAIL. The display
#: name is what the inbox shows as the sender; the prefix starts every
#: subject ("Exam Update: Your booking is confirmed").
MAILERS = {
    "exam": {"display_name": "TestMu AI Certifications", "subject_prefix": "Exam Update"},
    "reminders": {"display_name": "TestMu AI Certifications", "subject_prefix": "Reminder"},
    "results": {"display_name": "TestMu AI Certifications", "subject_prefix": "Results"},
    "staff": {"display_name": "TestMu AI Certifications", "subject_prefix": "Staff"},
}

#: The demo (PythonAnywhere) only: send each email to the person whose action
#: caused it — the candidate who booked, the admin who cancelled — instead of
#: to the candidate. Reviewers then receive what their own clicks trigger, and
#: nobody else is emailed. Emails from the scheduled job (reminders, expiry)
#: go to whoever made the booking. Off everywhere else; production never sets it.
EMAIL_SEND_TO_ACTOR = env_bool("EMAIL_SEND_TO_ACTOR", False)

#: Retries after a failed send: minutes to wait before attempts 2, 3, 4 and 5.
#: After EMAIL_MAX_ATTEMPTS the email is left as failed, with its last error.
EMAIL_RETRY_DELAYS_MINUTES = [1, 5, 15, 30]
EMAIL_MAX_ATTEMPTS = 5
#: Sent and skipped emails are deleted after this many days. Failed ones are
#: kept, for whoever looks into "I never got my email".
EMAIL_RETENTION_DAYS = 90
#: Reminders, in minutes before the start. Each is sent once, between its own
#: mark and the next one's — never after the exam has started.
EMAIL_REMINDER_MINUTES = [60, 30]
#: "Booking expired" goes this long after the join window closes: start + 45
#: minutes + 3 hours for an objective round, start + 36 hours + 3 hours for a
#: subjective one.
EMAIL_EXPIRED_DELAY_HOURS = 3
