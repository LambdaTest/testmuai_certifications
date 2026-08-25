# TestMu AI Certifications

In-house platform for delivering TestMu AI professional certifications — booking, exam delivery,
grading, and credential issuance. Replaces our current external vendor.

> **Status:** two journeys work end to end.
>
> - **Candidate** — book, reschedule, cancel, calendar invites, dashboard, assessments.
> - **Admin authoring** — Subject Center and Exam Center: create and edit subjects and exams,
>   with derived slugs, derived marks, and draft/publish.
>
> The examiner dashboard exists as a shell. The question bank, exam player, grading and
> credentials are not started. See [`docs/master-spec.md`](docs/master-spec.md).

## Stack

| Layer | Choice |
|---|---|
| Backend | Django 5.2 |
| Database | PostgreSQL 17 — everywhere, including local development |
| Frontend | Django templates + Tailwind + Alpine.js *(both from CDN, no build step yet)* |
| Background jobs | Celery + Redis *(not wired up — commented out in `requirements.txt`)* |
| Hosting | AWS — EC2/Elastic Beanstalk + RDS *(not set up yet)* |

## Running it

**Postgres first** — there is no SQLite fallback. `docker-compose.yml` has it pinned to the
version RDS runs:

```bash
docker compose up -d          # start (also brings up Redis, unused for now)
docker compose down           # stop, data survives
docker compose down -v        # stop and wipe the database
```

Then:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env

.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

Then <http://127.0.0.1:8000/book/>.

For the Django admin, create a superuser — note it takes `external_id`, not a username, since
that's our `USERNAME_FIELD`:

```bash
.venv/bin/python manage.py createsuperuser --external_id admin
```

A fresh database has no exams. Add them through **Exam Center → Add Exam** — the
`seed_certifications` command is currently broken, see [below](#seed_certifications).

**Database: Postgres everywhere, including local development.** There is deliberately no SQLite
fallback. SQLite differs on JSONB (which the question bank will lean on for polymorphic question
payloads and answer keys), on `timestamptz`, on constraint enforcement, and on concurrency. A
silent fallback means code that passes locally can behave differently in production — so if the
connection fails, start Postgres rather than working around it.

**Tailwind and Alpine both load from a CDN** so there's no build step. Before production, build
Tailwind with the standalone CLI (no Node needed) and swap the script tag in
`templates/base.html`:

```bash
tailwindcss -i static/css/input.css -o static/css/output.css --minify
```

Alpine being a CDN script matters more than it looks: several admin pages put their state in
`x-data`, so if that script fails to load the page still renders but stops reacting. Nothing
user-facing may depend on it for correctness — see [rule 2](#three-rules-to-know-before-writing-anything).

## Layout

```
config/         settings, root URLconf, wsgi/asgi
apps/
  home/         accounts and cross-cutting — User model, roles, dashboards, decorators
  exam/         the assessment domain — subjects, exams, bookings, and to come:
                questions, attempts, grading, credentials
templates/      base.html (public) + base_staff.html (admin shell) + per-app templates
static/         css/input.css, js/booking.js
docs/           specs — see below
archived/       the previous Next.js implementation, kept as UX reference
TRACKER.md      deferred work. Gitignored on purpose — it never ships.
```

**Two apps, deliberately.** `exam` is one cohesive domain: subjects, exams, questions, bookings,
attempts, grading, and credentials all constrain one another. `home` holds what isn't part of
that — accounts, roles, and the dashboards.

**Dependencies point one way.** `exam` reaches the user only through `settings.AUTH_USER_MODEL`
(a string, so no import); `home` may import from `exam`, never the reverse.

When `exam/models.py` outgrows a single file, split it into a `models/` package — not into
another app. App boundaries are baked into migrations and are expensive to move.

## Roles and access

`User.Role` is `candidate` · `examiner` · `admin`, defaulting to `candidate`. Access is enforced
with one decorator, `apps/home/decorators.py`:

```python
@role_required(User.Role.ADMIN)
def add_exam(request): ...
```

It applies `@login_required` internally, so it runs first, and raises `Http404` rather than
returning 403 — an admin URL shouldn't confirm it exists to someone who may not use it.

`/dashboard/` branches on role and renders one of `dashboard_candidate.html`,
`dashboard_examiner.html`, or `dashboard_admin.html`. Admin pages extend `base_staff.html`,
which carries the accordion sidebar; candidate pages extend `base.html`.

**Grading is blind.** The examiner sees a booking reference and the submitted answers — never
the candidate's name or email. Identity is resolvable only by an admin. Keep it that way when
building the grading screens: nothing in an examiner-facing view should `select_related` its way
to a candidate.

## Exam authoring

Two house rules live on the `Exam` model as constants, not scattered through forms and templates:

| Constant | Value | Meaning |
|---|---|---|
| `MARKS_PER_QUESTION` | `5` | Every objective question is worth the same, as on the vendor platform |
| `DEFAULT_PASS_RATIO` | `0.7` | Applied when an author leaves the pass mark blank |

Uniform marks are what make an absolute pass mark safe against a randomised paper: a draw of
N questions always totals N × 5, whoever sits it. That's why pass marks are stored as absolute
numbers and not percentages.

**Maximum marks is derived, never typed.** `Exam.total_marks_for(selection, count)` is the single
definition; both `Exam.save()` and `ExamForm.clean()` call it, so the number validated is exactly
the number stored. It is deliberately not a form field — a `readonly` input would still post its
value and can be edited in devtools.

**Duration is derived too**, from `exam_type` — 45 minutes objective, 36 hours subjective — and a
`CheckConstraint` enforces the pair, so a mismatched row can't be written by any route.

**Question selection** is `random` or `manual`. Only random works: the manual picker needs an
`Exam ↔ Question` relation that doesn't exist yet, so publishing a manual exam is refused in
`ExamForm.clean()` and its Publish button is disabled. The team confirmed manual selection has
never been used on the vendor platform, so it's deferred rather than built on spec.

> **Nothing checks the question count against the bank.** An exam can promise 40 questions from
> a subject holding 12. That check needs the bank to exist, and it belongs at publish time *and*
> at attempt start — the bank changes after an exam is saved, so a form check would go stale.

## Three rules to know before writing anything

**1. Timezone conversion happens in one place.** `apps/exam/timezones.py` owns every
conversion between a candidate's wall-clock choice and the stored UTC instant. Times are stored
UTC and displayed in the zone the candidate booked in, always with the offset labelled. A
candidate who misreads their booking time misses their exam, and it is unrecoverable.

**2. The client is display only.** The date picker disables past days and caps the horizon; the
Publish button greys out for a manual exam. Both are explanations, not enforcement — a form post
can be made directly, and an Alpine binding never applies at all if the CDN script fails to load.
Every rule that must hold of a stored row is re-checked server-side.

**3. A pre-converted datetime does not survive a template filter.** With `USE_TZ = True`, Django's
`date` filter converts aware datetimes to `settings.TIME_ZONE` — UTC — before formatting, silently
undoing any conversion done in Python. Render the raw field inside `{% timezone %}` instead. See
[`docs/conventions.md`](docs/conventions.md#timezones).

`docs/conventions.md` also sets out the four places a rule can live — database constraint, model
`clean()`, form `clean()`, view check — and which to reach for. Constraints are the only real
guarantee; `bulk_create` bypasses `save()`.

## Booking model

**Self-scheduled, not slot-based.** Candidates pick their own date and time. There are no
pre-defined slots and no capacity, so there is no seat contention. Rules live in `settings.py`:

- `BOOKING_MIN_DAYS_AHEAD = 1` — no same-day booking
- `BOOKING_MAX_MONTHS_AHEAD = 3`
- `BOOKING_GAP_MINUTES = 60` — clear time required either side of an exam a candidate has
  already booked. An objective exam occupies its full duration; a subjective one is a
  36-hour window with a deadline, so it only blocks around its start.

A candidate may hold only one open booking per exam, enforced by a partial unique index
(`one_open_booking_per_exam`) rather than a view check.

## Management commands

Custom `manage.py` subcommands live in `apps/<app>/management/commands/`. Any file there with a
`Command` class becomes a subcommand named after the file — both `__init__.py` files are required
or Django silently won't find it.

### `seed_certifications`

**Currently broken.** It writes `name` and `level`, which were renamed to `exam_name` and
`exam_level` when `exam_level` moved from `Subject` to `Exam`:

```
FieldError: Invalid field name(s) for model Exam: 'level', 'name'.
```

It also predates `Exam.subject` becoming a required FK, so fixing the field names alone won't be
enough — each seeded exam now needs a subject to belong to. Until then, add exams through Exam
Center.

When it is fixed, the design it had is worth keeping:

- **Idempotent.** `update_or_create` matched on **slug**, which is the identity.
- **It overwrites admin edits to the fields it owns.** That's intentional — the seed is the
  source of truth for those fields — so anything that should be admin-editable must come *out*
  of `defaults`.
- **It never deletes.** Removing an entry leaves the row in place. Deleting an exam that has
  bookings or issued credentials against it must never be a side effect of running a seed script.

Seed scripts are preferred over hand-entry through the admin — repeatable for fresh local
databases, staging, and CI, and they show up in a diff. Recurring work (expiring abandoned
attempts, releasing results) becomes a Celery task instead, not a command someone has to cron.

## Documentation

Specs live in [`docs/`](docs/), all rewritten for Django:

| Document | Covers |
|---|---|
| [`docs/master-spec.md`](docs/master-spec.md) | Purpose, scope, open decisions |
| [`docs/auth.md`](docs/auth.md) | The OIDC handoff from TestMu AI's login |
| [`docs/conventions.md`](docs/conventions.md) | Where rules live, timezones, naming |
| [`docs/routes.md`](docs/routes.md) | URL map and where new routes belong |

`scripts/build-spec.py` regenerates `master-spec.docx` from the markdown.

## Not yet built

The question bank and `Exam ↔ Question` relation · attempts and the exam player · grading and
result release · credentials and public verification · Candidate Center · authentication (the
OIDC integration with the TestMu AI login is deferred, which is why `ExamBooking.candidate` is
nullable) · automated tests · the Tailwind production build.

`TRACKER.md` holds the full list.
