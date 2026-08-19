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

**Postgres first** — there is no SQLite fallback. Either:

```bash
# Docker
docker run -d --name testmuai-pg -p 5432:5432 \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=testmuai_certifications \
  postgres:17

# or Homebrew
brew install postgresql@17 && brew services start postgresql@17
createdb testmuai_certifications
```

Then:

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

**Database: Postgres everywhere, including local development.** There is deliberately no SQLite
fallback. SQLite differs on JSONB (which the question bank will lean on for polymorphic question
payloads and answer keys), on `timestamptz`, on constraint enforcement, and on concurrency. A
silent fallback means code that passes locally can behave differently in production — so if the
connection fails, start Postgres rather than working around it.

**Tailwind** currently loads from a CDN so there's no build step. Before production, build with
the standalone CLI (no Node needed) and swap the script tag in `templates/base.html`:

```bash
tailwindcss -i static/css/input.css -o static/css/output.css --minify
```

## Layout

```
config/         settings, root URLconf, wsgi/asgi
apps/
  home/         accounts and cross-cutting — User model, dashboard (later)
  exam/         the assessment domain — certifications, bookings, and to come:
                exam versions, questions, attempts, grading, credentials
templates/      base.html + per-app templates
static/         css/input.css, js/booking.js
archived/       the previous Next.js implementation — see below
```

**Two apps, deliberately.** `exam` is one cohesive domain: certifications, exam versions,
questions, bookings, attempts, grading, and credentials all constrain one another. `home` holds
what isn't part of that — accounts, and the candidate dashboard once it exists.

**Dependencies point one way.** `exam` reaches the user only through `settings.AUTH_USER_MODEL`
(a string, so no import); `home` may import from `exam`, never the reverse.

When `exam/models.py` outgrows a single file, split it into a `models/` package — not into
another app. App boundaries are baked into migrations and are expensive to move.

## Management commands

Custom `manage.py` subcommands live in `apps/<app>/management/commands/`. Any file there with a
`Command` class becomes a subcommand named after the file — both `__init__.py` files are required
or Django silently won't find it.

### `seed_certifications`

Creates or updates the 22-certification catalog. Matched on **slug**, which is the identity.

```bash
.venv/bin/python manage.py seed_certifications
```

| | Fields |
|---|---|
| **Written on every run** | `name` · `level` · `status` (always `published`) · `marketing_url` (derived from the slug) |
| **Left alone** | `description` · `icon_url` · `external_ref` |

Three things to know:

- **Idempotent.** Uses `update_or_create`, so re-running updates rather than duplicating.
- **It overwrites admin edits to the fields it owns.** Rename a certification through the Django
  admin and the next run reverts it. That's intentional — the seed is the source of truth for
  those four fields — so anything that should be admin-editable must come *out* of `defaults`.
- **It never deletes.** Removing an entry from `CERTIFICATIONS` leaves the row in place.
  Deleting a certification that has bookings or issued credentials against it must never be a
  side effect of running a seed script.

> **Everything it seeds is `published`, so everything is bookable.** Fine for a demo, wrong for
> real: a certification shouldn't be bookable until it has a published exam version with
> questions behind it. `Certification.is_bookable` currently checks only status and needs the
> version check once exam versions exist.

Seed scripts are preferred over hand-entry through the admin — repeatable for fresh local
databases, staging, and CI, and they show up in a diff. Recurring work (expiring abandoned
attempts, releasing results) becomes a Celery task instead, not a command someone has to cron.

## Two rules to know before writing anything

**1. Timezone conversion happens in one place.** `apps/exam/timezones.py` owns every
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

The previous Next.js implementation, kept as a working reference for the booking UX.
Nothing in the running app depends on it.

## Documentation

Specs live in [`docs/`](docs/). They were written for the Next implementation and
mostly survived the move to Django — the data model, the auth design and the
conventions still apply. Two need attention:

| Document | State |
|---|---|
| [`docs/master-spec.md`](docs/master-spec.md) | Current — purpose, scope, open decisions |
| [`docs/auth.md`](docs/auth.md) | Current — the OIDC handoff from TestMu AI's login |
| [`docs/conventions.md`](docs/conventions.md) | Mostly — the Vercel and serverless sections no longer apply |
| [`docs/routes.md`](docs/routes.md) | **Stale** — describes Next route groups, needs rewriting for Django URLs |

`scripts/build-spec.py` regenerates `master-spec.docx` from the markdown.

## Not yet built

Exam versions · sections · question bank · attempts · the exam player · grading · result release ·
credentials and public verification · the candidate dashboard · admin beyond Django's default ·
authentication (the OIDC integration with TestMu AI's login is deferred — `Booking.candidate` is
nullable until it lands).
