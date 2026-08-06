# TestMu AI Certifications

In-house platform for delivering TestMu AI professional certifications — booking, exam delivery,
grading, and credential issuance. Replaces our current external vendor.

> **Status:** early. The booking page works end to end; everything after it is still to build.

## Stack

| Layer | Choice |
|---|---|
| Backend | Django 5.x |
| Database | PostgreSQL (SQLite locally with no setup) |
| Frontend | Django templates + Tailwind + Alpine.js |
| Background jobs | Celery + Redis *(not wired up yet)* |
| Hosting | AWS — EC2/Elastic Beanstalk + RDS *(not set up yet)* |

## Running it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env

.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_certifications
.venv/bin/python manage.py runserver
```

Then <http://127.0.0.1:8000/book/>.

For the Django admin, create a superuser — note it takes `external_id`, not a username, since
that's our `USERNAME_FIELD`:

```bash
.venv/bin/python manage.py createsuperuser --external_id admin
```

**Database:** SQLite by default so the project runs with no setup. Postgres is the target for
staging and production — set `DATABASE_URL` to use it, and do so before relying on any
database-level constraint behaviour.

**Tailwind** currently loads from a CDN so there's no build step. Before production, build with
the standalone CLI (no Node needed) and swap the script tag in `templates/base.html`:

```bash
tailwindcss -i static/css/input.css -o static/css/output.css --minify
```

## Layout

```
config/                 settings, root URLconf, wsgi/asgi
apps/
  accounts/             User model — keyed on the OIDC `sub`, no passwords
  certifications/       Certification catalog + seed command
  bookings/             Booking model, form, view, timezone helpers
templates/              base.html + per-app templates
static/                 css/input.css, js/booking.js
archived/               the previous Next.js implementation — see below
```

## Two rules to know before writing anything

**1. Timezone conversion happens in one place.** `apps/bookings/timezones.py` owns every
conversion between a candidate's wall-clock choice and the stored UTC instant. Times are stored
UTC and displayed in the zone the candidate booked in, always with the offset labelled. A
candidate who misreads their booking time misses their exam, and it is unrecoverable.

**2. The client is display only.** The date picker disables past days and caps the horizon, but
a form post can be made directly — so `BookingForm` re-checks every rule server-side. Never let a
UI guard be the only guard.

## Booking model

**Self-scheduled, not slot-based.** Candidates pick their own date and time. There are no
pre-defined slots and no capacity, so there is no seat contention. Rules live in `settings.py`:

- `BOOKING_MIN_DAYS_AHEAD = 1` — no same-day booking
- `BOOKING_MAX_MONTHS_AHEAD = 3`

## `archived/`

The previous Next.js implementation, kept as a working reference for the booking UX. Also holds
the specs, which are still current and largely stack-independent:

| Document | Still applies |
|---|---|
| `archived/docs/master-spec.md` | Yes — scope, flow, open decisions |
| `archived/docs/auth.md` | Yes — the OIDC handoff from TestMu AI's login |
| `archived/docs/conventions.md` | Mostly — ignore the Vercel/serverless sections |
| `archived/src/db/README.md` | Yes — the data model to build out |
| `archived/docs/routes.md` | Concepts only — Next route groups, not Django URLs |

These need migrating into `docs/` properly. Until then, treat them as the source of truth for
anything not yet built.

## Not yet built

Exam versions · sections · question bank · attempts · the exam player · grading · result release ·
credentials and public verification · the candidate dashboard · admin beyond Django's default ·
authentication (the OIDC integration with TestMu AI's login is deferred — `Booking.candidate` is
nullable until it lands).
