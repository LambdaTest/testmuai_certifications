# TestMu AI Certifications

In-house platform for delivering TestMu AI professional certifications — booking, exam delivery,
grading, and credential issuance. Replaces our current external vendor.

> **Status:** three journeys work end to end.
>
> - **Candidate** — book, reschedule, cancel, calendar invites, dashboard, assessments.
> - **Admin authoring** — Subject Center and Exam Center: create and edit subjects and exams,
>   with derived slugs, derived marks, and draft/publish.
> - **Question Center** — write questions with answer options and media, browse the bank, or
>   bulk-import from CSV with a preview step.
>
> The exam player is the current work: its models are in place, the view is a stub. The examiner
> dashboard exists as a shell. Grading and credentials are not started. See
> [`docs/master-spec.md`](docs/master-spec.md).

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
fallback. SQLite differs on partial unique indexes (`one_open_booking_per_exam`), on
`timestamptz`, on `CheckConstraint` enforcement, on the `UniqueConstraint`s guarding an exam
sheet, and on concurrency. A
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
  exam/         the assessment domain — subjects, exams, questions, bookings, exam sheets,
                and to come: grading and credentials
    imports.py  CSV parsing for the question importer — plain functions, no request, no forms
    calendar.py .ics generation
    timezones.py the one place a wall-clock time becomes a UTC instant
templates/      base.html (public) + base_staff.html (admin shell) + per-app templates
static/         css/input.css, js/booking.js, imports/questions-template.csv
media/          runtime uploads — question images, audio, video. Gitignored.
docs/           specs — see below
archived/       the previous Next.js implementation, kept as UX reference
TRACKER.md      deferred work. Gitignored on purpose — it never ships.
```

**Two apps, deliberately.** `exam` is one cohesive domain: subjects, exams, questions, bookings,
exam sheets, grading, and credentials all constrain one another. `home` holds what isn't part of
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
> a subject holding 12, and nothing says so until a candidate presses Start Test and the draw
> comes up short. The bank now exists, so the check is buildable — but it belongs at publish time
> *and* at Start Test, because the bank keeps changing after an exam is saved and a form check
> alone would go stale.

## Question bank

**Questions belong to a subject, not to an exam.** Any exam on that subject draws from the pool
automatically, which is why there is nothing to attach by hand and no `Exam ↔ Question` table.

Three pages under Question Center:

| Page | What it does |
|---|---|
| **Question Bank** | Read-only list. Cards expand to show options, media and which exams can draw the question |
| **Add Question** | One question and its answer options in a single post |
| **Import Questions** | Bulk CSV import with a preview step |

**The bank is read-only on purpose.** A question that has been sat is the record of what a
candidate was asked, so editing its wording after the fact rewrites history that grading and
appeals depend on. There is no edit page and no plan for one. That immutability is also what lets
`ExamSheetQuestion` reference a question by foreign key instead of snapshotting its text.

**Retiring, not deleting.** `Question.status` is `active` or `retired`. Retiring drops a question
out of the bank listing and out of random draws without losing the row. Both DELETE buttons are
still `href="#"` and `delete_question` is a stub — see `TRACKER.md` for the gated-delete design.

**Answer options are an inline formset.** `AnswerOptionFormSet` renders six slots and shows four;
blank ones are skipped rather than saved as empty rows. The rules that span rows — at least two
options, exactly one correct, none at all on a subjective question — live in the formset's
`clean()`, because a single option knows nothing about its siblings and Postgres can only check a
row against itself.

`AnswerOptions.position` records the order the author wrote them, assigned by the formset's
`save()`. Without it the options come back in whatever order Postgres returns, and that order can
differ between two reads — a candidate would watch the answers rearrange between page loads.

**Media is uploaded, not chosen.** `Question.associated_image` and friends are foreign keys to
`Image`, `Audio` and `Video`, so a plain ModelForm would render dropdowns of existing rows. The
forms declare `FileField`s under separate names instead and create the row on save. One model per
type rather than one generic `Media`, so the accepted extensions are declared on the field and
validate themselves.

> The extension validators are **re-declared on the form**. `Model.save()` never calls
> `full_clean()`, so `Image.objects.create(...)` runs no validation at all — a model-field
> validator only fires when a ModelForm validates that model. Size is checked only on the form:
> Django applies no upload ceiling of its own.

Uploads land under `MEDIA_ROOT` (`media/`, gitignored), served by Django in development only.
Before production this becomes S3 via a storage backend — an EC2 instance that gets replaced
loses every upload, and two instances disagree about what exists.

**CSV import is two-phase.** Uploading parses and shows what *would* happen; a second submit
commits. A bulk import that writes on the first click gives an author no way to notice they picked
last month's file until two hundred questions are in the bank, and there is no bulk undo. The
parsed rows wait in the session between the two requests — not the cache, which is per-process.

Parsing lives in `apps/exam/imports.py`: plain functions taking data and returning data, no
request and no form. That is what lets the same code serve a management command when the vendor's
bank has to be migrated across.

> **There is no test for "is this really a CSV"**, because there isn't one to write. CSV has no
> magic bytes and no header — any text file is a valid CSV of one column. What `read_csv` checks
> is that the bytes decode as text, contain no NUL, and carry the columns we need. The decode and
> NUL checks exist purely for the error message: without them, uploading a spreadsheet reports
> `line contains NUL` instead of "save it as CSV".

Imports are deliberately partial — bad rows are skipped and reported, the rest go in. One typo in
five hundred rows should not cost the other 499, because an author facing a full re-upload deletes
the awkward row rather than fixing it.

`import_rows` feeds `QuestionForm` and `AnswerOptionFormSet` rather than calling
`Question.objects.create()`, so there is one definition of a valid question. Marks forcing and tag
normalisation apply to imported rows for free.

## Exam delivery

Two models, added ahead of the player itself.

**`ExamSheet`** is the paper one candidate sat — a `OneToOneField` to their booking, plus
`started_at`, `expires_at`, `current_position` and `submitted_at`. **`ExamSheetQuestion`** is one
served question and its answer: `position`, a `marks` snapshot, `selected_option`,
`written_answer` and `marks_awarded`.

**The paper is fixed when the candidate presses Start Test**, never at booking. Between booking
and sitting the bank changes, and a paper drawn weeks ahead could serve a question since retired.
Drawing lazily as the candidate presses Next is worse still: it re-randomises on a reload, makes
"question 3 of 20" a promise that cannot be kept, and turns a double-clicked Next into a race.

**A reconnect resumes, it does not restart.** `current_position` is the candidate's bookmark, so
a dropped connection returns them to the question they were on rather than the beginning. The
deadline is `expires_at` on the server — a deadline the browser can report is a deadline a
candidate can extend. Answers autosave per question; that, not the bookmark, is what actually
protects their work.

**`submitted_at` is one timestamp, not a state machine.** Pressing Submit, running out of time and
being stopped by an admin are all "this paper is finished", and the score is the same in each case.
Set it with `min(timezone.now(), expires_at)` so a paper abandoned at 10:00 and swept up at 14:00
records when the exam actually ended.

**`on_delete=PROTECT` on `ExamSheetQuestion.question` is load-bearing.** Once a question appears on
any sheet, deleting it raises at the database level — not because a view remembered to check. That
is the delete gate, enforced structurally; questions never served stay freely deletable. Two unique
constraints do the same job for the draw: no two questions in one slot, and no question twice on
one paper.

**Options are not shuffled per candidate.** Drawing 20 questions from a pool of several hundred
already means two candidates share barely one question, and shuffling breaks any option that
depends on where it sits — "All of the above" being the obvious one. Every candidate sees the
authored order.

> **The draw must filter on question type.** Nothing in the models stops an objective exam serving
> a subjective question, which would break `total_marks_for()`'s arithmetic. That belongs in
> whatever builds the sheet.

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

The exam player itself — `exam_player` and `delete_question` are routed but stubbed · grading and
result release · credentials and public verification · Candidate Center · authentication (the
OIDC integration with the TestMu AI login is deferred, which is why `ExamBooking.candidate` is
nullable) · automated tests · the Tailwind production build.

Two smaller gaps worth knowing: **marking a question for review** is in the player's design but
has no field on `ExamSheetQuestion` yet, and **media rows are mutable** — replacing the file on an
`Image` row would change what a past paper appears to have shown.

`TRACKER.md` holds the full list.
