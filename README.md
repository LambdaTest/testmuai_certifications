# TestMu AI Certifications

In-house platform for delivering TestMu AI professional certifications — booking, exam delivery,
grading, and credential issuance. Replaces our current external vendor.

> **Status:** eight journeys work end to end.
>
> - **Candidate** — book, or start an exam instantly; reschedule and cancel (until 10 minutes before), calendar invites,
>   dashboard, and My Assessments lists that follow the clock, not only the stored status.
> - **Admin authoring** — Subject Center and Exam Center: create and edit subjects and exams
>   (objective, subjective, or both rounds), with derived slugs, derived marks, and draft/publish.
> - **Question Center** — write questions with answer options and media, browse the bank, or
>   bulk-import from CSV with a preview step.
> - **Objective exam** — join inside the booked window, T&C, a full-screen timed player with
>   autosave, review flags and resume after a dropped connection, submit or time-out, automatic
>   grading, and a completion page showing the score.
> - **Subjective exam** — join inside the 36-hour window, submit a GitHub repository, a pull
>   request in it and Test Manager test IDs; on a two-round exam it follows the objective round
>   automatically.
> - **Grading** — an admin assigns each submitted subjective paper to an examiner or admin; the
>   assignee grades it blind from My Tasks, and Grading History lists what they have graded.
>   Examiners have their own simpler layout and dashboard.
> - **Candidate Center** (admins) — Candidate Info (search, a page per candidate with every
>   booking), Book Exam on a candidate's behalf, Cancel Exam with a reason, and Export Candidates
>   to CSV.
>
> - **Email** — booking, reschedule, cancellation, reminder, second-round and expiry emails with
>   calendar invites, through an outbox with retries; a scheduled job sends reminders and closes
>   missed bookings. Tested against Mailpit; production sending waits on IT's Gmail App Password.
>
> Not started: combined two-round results against the pass percentage, result release, and
> credentials. See [`docs/master-spec.md`](docs/master-spec.md).

## Stack

| Layer | Choice |
|---|---|
| Backend | Django 5.2 |
| Database | PostgreSQL 17 — everywhere, including local development |
| Frontend | Django templates + Tailwind + Alpine.js *(both from CDN, no build step yet)* |
| Background jobs | `manage.py run_scheduled_jobs`, every minute (cron; an always-on `--loop` task on PythonAnywhere): reminders, missed bookings, abandoned papers, sending and retrying email, cleanup. Celery + Redis only if heavier work appears *(not wired up — commented out in `requirements.txt`)* |
| Email | SMTP through `apps/exam/emails` — Mailpit locally, Gmail in production *(waiting on IT for the App Password)* |
| Hosting | AWS — EC2/Elastic Beanstalk + RDS *(not set up yet)* |

## Running it

**Postgres first** — there is no SQLite fallback. `docker-compose.yml` has it pinned to the
version RDS runs:

```bash
docker compose up -d          # start Postgres, Mailpit (email inbox at http://localhost:8025)
                              # and Redis (unused for now)
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
sheet, and on concurrency — it has one writer for the whole database, and `select_for_update()`,
which autosave and submit rely on, is silently ignored. `SubjectiveSubmission.test_ids` is also an
`ArrayField`, which exists only on Postgres (`django.contrib.postgres.fields`). A
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
  home/         accounts and cross-cutting — User model, roles, dashboards, decorators, and
                the admin Candidate Center pages that are about people (Candidate Info,
                Export Candidates)
    exports.py  Export Candidates: the fixed column lists and the CSV writer
  exam/         the assessment domain — subjects, exams, questions, bookings, exam sheets,
                grading, and to come: credentials
    emails/     outbound email: queue_email(), the event registry, the sender, the job steps
    sweeps.py   booking housekeeping for the scheduled job (missed bookings)
    imports.py  CSV parsing for the question importer — plain functions, no request, no forms
    calendar.py .ics generation
    timezones.py the one place a wall-clock time becomes a UTC instant
templates/      base.html (public) + base_staff.html (admin shell) + base_examiner.html
                (examiner shell) + per-app templates
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
which carries the accordion sidebar; examiner pages extend `base_examiner.html`, a shorter
sidebar (Dashboard, My Tasks, Grading History); candidate pages extend `base.html`. A page both
roles use (My Tasks, the grading page, Grading History) takes the layout from its view —
`{% extends layout|default:"base_staff.html" %}` — so each role keeps its own sidebar.

**Grading is blind.** The examiner sees a booking reference and the submitted answers — never
the candidate's name or email. Identity is resolvable only by an admin. Keep it that way when
building the grading screens: nothing in an examiner-facing view should `select_related` its way
to a candidate.

## Exam authoring

**An exam is objective, subjective, or both.** `exam_type` is `objective`, `subjective` or
`both`; a "both" exam is sat as two rounds — see [Two-round exams](#two-round-exams).

The house rules live on the `Exam` model as constants, not scattered through forms and templates:

| Constant | Value | Meaning |
|---|---|---|
| `MARKS_PER_QUESTION` | `5` | Every objective question is worth the same, as on the vendor platform |
| `SUBJECTIVE_QUESTION_COUNT` | `1` | A subjective round is one task |
| `SUBJECTIVE_MARKS` | `50` | What that task is worth |
| `DEFAULT_PASS_PERCENTAGE` | `70` | Applied when an author leaves the pass mark blank |
| `ROUND_GAP_MINUTES` | `30` | Gap between submitting the objective round and the subjective round opening |

**The pass mark is a percentage** (`pass_percentage`, whole percent), not an absolute number. On a
two-round exam the pass is 70% of both rounds together, and subjective questions in a pool need
not all carry the same weight — an absolute figure would be right for some candidates and wrong
for the rest.

**Maximum marks is derived, never typed.** `Exam.total_marks_for(exam_type, question_count)` is
the single definition — `count × 5`, `50`, or `count × 5 + 50` — and both `Exam.save()` and
`ExamForm.clean()` call it, so the number validated is exactly the number stored. It is
deliberately not a form field — a `readonly` input would still post its value and can be edited in
devtools.

**Duration is derived too**, from `Exam.DURATION_BY_TYPE` — 45 minutes objective, 36 hours
subjective, and the sum for "both" — and a `CheckConstraint` enforces the pair, so a mismatched row
can't be written by any route. The "both" figure is a total **for display only**: the rounds are
separate sittings with their own clocks, so anything that times a sitting uses the *round's*
duration, never `exam.duration_minutes`.

**Every paper is a random draw.** `question_selection` is commented out of `ExamForm`, not removed
from the model: manual selection was never used on the vendor platform and its picker was never
built.

> **The question count is checked at Start Test, not at publish.** `_start_or_resume` refuses to
> draw when the subject's active pool is smaller than the paper, with a message to contact support.
> An exam can still be *published* promising 40 questions from a subject holding 12 — a publish-time
> check is still to build, and it would not replace this one, because the bank keeps changing after
> an exam is saved.

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

### The models

**`ExamSheet`** is the paper one candidate sat — a `OneToOneField` to their booking, plus
`started_at`, `expires_at`, `current_position`, `submitted_at` and `submission_status` (`self` or
`timedout`). **`ExamSheetQuestion`** is one served question: `position`, a `marks` snapshot,
`selected_option`, `flagged` (the candidate's review mark) and `marks_awarded`.

**`SubjectiveSubmission`** is a subjective round's answer, one-to-one with its
`ExamSheetQuestion`: `github_repo`, `github_pr`, `test_ids` (an `ArrayField` of Test Manager IDs)
and `submitted_at`. It is a separate model rather than columns on `ExamSheetQuestion` so its fields
can be genuinely required — on the shared row they would have to be optional, because forty
objective rows per paper never have them. The question slot, its marks and `marks_awarded` stay on
`ExamSheetQuestion` for both kinds of round.

### Joining

**There is a join window.** `ExamBooking.join_closes_at` is `scheduled_at` plus the *round's*
duration; `ExamBooking.stage` reads `upcoming` before the window, `underway` inside it and `lapsed`
after. A booking for 10:00 PM on a 45-minute round can be started from 10:00 to 10:45.

- **Join exam** (assessment page and dashboard) is a live link only while `underway`; otherwise a
  disabled button. Reschedule and Cancel close earlier, `BOOKING_CHANGE_CUTOFF_MINUTES` (10) before
  the start (`ExamBooking.can_change`); Add to calendar works until the window has passed. Once
  lapsed, all of them are disabled.
- **The server enforces the same window.** `_start_or_resume` refuses to draw a *new* paper before
  `scheduled_at` or after `join_closes_at`. The buttons are display; this check is what holds.
- **Whoever starts inside the window gets the full duration from the moment they press begin** —
  a 10:44 start runs to 11:29.
- **Getting back in after the window has closed** is by the link in the reminder emails (planned,
  60 and 30 minutes before the start), which leads to the T&C page; begin there resumes an existing
  paper whatever the time.

The T&C page is reachable by GET at any time on purpose: reading the rules changes nothing, and the
begin POST is where the window is checked. After begin it sends each round to its own player —
`exam_player` for objective, `exam_player_subjective` for subjective — and each player redirects a
round of the other kind to the right one, so a bookmarked or typed URL cannot open a paper in the
wrong player.

**Durations are per round on every booking page.** `ExamBooking.duration_display` shows "45 min"
or "36 hrs" and the pages label a booking with its round, not the exam's type — on a two-round exam
`Exam.duration_display` ("45 min + 36 hrs") and the type "Both" describe the whole exam and appear
only in the exam catalogue. Calendar invites (`.ics` and Google Calendar) use the round's duration
too: a 45-minute block for an objective round, a capped one-hour block plus a "Submit by" deadline
for a subjective one.

### Sitting the paper

**The paper is fixed when the candidate presses begin**, never at booking. Between booking and
sitting the bank changes, and a paper drawn weeks ahead could serve a question since retired.
Drawing lazily as the candidate presses Next is worse still: it re-randomises on a reload, makes
"question 3 of 20" a promise that cannot be kept, and turns a double-clicked Next into a race.

**The draw filters on the round's type**, `booking.round_type`, not the exam's — an exam can be
"both", a question never is.

**A reconnect resumes, it does not restart — and it does not stop the clock.** `expires_at` is
fixed at begin and never moves; the player computes time left from it on every load. Rejoining
always returns the same paper, even after the join window has closed, but someone who drops at 15
minutes left and returns 5 minutes later has 10. After `expires_at` the page submits itself as a
timeout. A deadline the browser can report is a deadline a candidate can extend, so the browser's
countdown is display only.

**Autosave.** Every answer, clear, flag and move posts to `save_answer` (`…/save/`), which writes
`selected_option`, `flagged` and `current_position` and answers in JSON:

- **One request at a time, in order**, through a queue — two answers sent in parallel can land in
  either order, and the server would keep whichever arrived last.
- **"Saved" shows only on the server's `{"ok": true}`**; a failure after three tries says "Not
  saved" instead.
- **`SaveAnswerForm` is a plain `Form`, not a `ModelForm`**: the browser can say "question 3,
  option 812, flagged" and nothing else. The view resolves the sheet and question from the
  candidate's own booking and refuses an option belonging to another question.
- **It refuses once the paper is closed** — submitted, past `expires_at`, or the booking no longer
  `booked` — with 409, and locks the sheet row (`select_for_update`) so a save cannot land after
  the final submit.
- **Absent and empty are different.** The view checks `"option_id" in request.POST` and
  `"flagged" in request.POST` rather than `cleaned_data`, which turns both into `None`/`False` —
  otherwise every answer save would unflag its question.

Rejoining hands back each saved option and flag, so the paper reappears as it was left.

**Lockdown is deterrent, not enforcement.** The objective player runs full screen, blocks the
context menu, copy and cut, stops text selection on the question pane, and hides the paper behind
an opaque screen when full screen is left. All of it is defeatable from devtools. The page tells candidates exits are recorded
— nothing records them yet.

**The answer key never reaches the browser.** The player's payload is built field by field — option
`id` and `text`, never `is_correct` — and `save_answer` replies the same way whether an answer is
right or wrong.

### Submitting

`submit_exam` is POST-only and runs in one transaction, holding a lock on the sheet:

1. Refuses a repeat (already submitted) or a booking that is not `booked`.
2. **For a subjective round, validates and saves the answer first** — see
   [The subjective round](#the-subjective-round). A rejected or late answer stops here, so the
   round stays open.
3. Stamps `submitted_at = min(now, expires_at)`, so a late POST records when the exam actually
   ended. `submission_status` is `self` only for a submission made before the deadline (the form
   sends `action=submit_action`); the timer's own POST, or anything after `expires_at`, is
   `timedout`.
4. Runs `grade_exam`. The booking is already `attended` — beginning set it.
5. On the objective round of a "both" exam, creates the subjective booking.

Every round, objective or subjective, is finished in this one function.

The Submit button opens a "Ready to submit?" dialog with answered, unanswered and flagged counts.
Both Submit and the timer wait (up to 5 seconds) for queued autosaves before posting, so a last
answer in flight is not refused as late.

**`submitted_at` is one timestamp, not a state machine.** Pressing Submit, running out of time and
being stopped by an admin are all "this paper is finished", and the score is the same in each case.

**Grading.** `grade_exam` marks objective rounds at submit: each question gets its `marks` snapshot
if the chosen option is correct and `0` otherwise (unanswered included), and the booking's
`marks_obtained` is set to the total — assigned, not added, so rerunning it is safe. Subjective
rounds are graded by an examiner and stay `None` until then; `None` means "not graded", which is
why it is not defaulted to `0`.

**The completion page** (`exam_completed.html`) shows "You Scored: N" for an objective round, and
after the first round of a two-round exam, a pointer to My Assessments for the second. It also
collects LinkedIn and GitHub (required) plus three 1–5 ratings and suggestions — **none of which is
saved yet.** `submit_exam` redirects to it (`…/<booking_id>/completed/`) rather than rendering it
as the reply to the POST, so a refresh is a harmless GET. The page reads everything from the
booking, is owned by the candidate, and refuses while the paper is still open.

### Two-round exams

A "both" exam is two bookings. `ExamBooking.round_type` says which round a booking is;
`parent_booking` (on the subjective booking, one-to-one) links it to its objective round — that
link is what lets the two be treated as one attempt, since the pass is 70% of both together.

- The candidate books once; that booking is the objective round.
- Submitting it creates the subjective booking, scheduled `ROUND_GAP_MINUTES` (30) after the
  objective was submitted, in the same timezone.
- The subjective round is a 36-hour window, joined from My Assessments.

`BookingForm.save()` sets `round_type` to `subjective` for a subjective-only exam and `objective`
otherwise.

### The subjective round

A separate page, `exam_player_subjective.html` at `exam/player/subjective/<booking_id>/`:
instructions, the task shown in full on the page (not a downloadable PDF as on the vendor platform),
and three required fields — the GitHub repository (private, shared with the admin address), a pull
request **in that repository**, and the Test Manager test IDs. The red Submit enables only when all
three are valid. There is no full-screen or copy lockdown: it is a 36-hour task done in an editor
and on GitHub, and blocking copy would stop the candidate pasting their links. There is no autosave
either — the answer is three links written once, not work in progress.

**The page is display only (`@require_GET`); the form posts to `submit_exam`.** There the answer is
validated and saved inside the same transaction that closes the round, before anything is stamped:

- an answer after `expires_at` is refused — unlike an objective paper, this POST *is* the answer;
- a rejected answer is rendered back into the same template with the bound form, so each field
  shows its server error and the candidate's values are put back (seeded through `data-*`
  attributes, since `x-model` owns the inputs);
- a valid answer is saved with `form.save(commit=False)` and `entry` set by the view — `entry` is
  never a form field, so the browser cannot attach an answer to another paper.

`ExamSheetFormSubjective` repeats every browser check: GitHub-only URL patterns (with or without
`www.`), the PR belonging to the repository, and test IDs split on commas or new lines, blanks and
repeats dropped, returned as a list for the `ArrayField`. Links are stored normalised — no `www.`,
no trailing slash, no `/files` tab — so one repository is always one string. Subjective rounds are
not auto-graded: `marks_obtained` stays `None` until an examiner marks them, and the completion
page shows no score.

### Integrity rules worth knowing

**`on_delete=PROTECT` on `ExamSheetQuestion.question` is load-bearing.** Once a question appears on
any sheet, deleting it raises at the database level — not because a view remembered to check. That
is the delete gate, enforced structurally; questions never served stay freely deletable. Two unique
constraints do the same job for the draw: no two questions in one slot, and no question twice on
one paper.

**Options are not shuffled per candidate.** Drawing 20 questions from a pool of several hundred
already means two candidates share barely one question, and shuffling breaks any option that
depends on where it sits — "All of the above" being the obvious one. Every candidate sees the
authored order. Autosave sends an option's **id**, not its position in the list, so the saved
answer cannot change even if the order did.

## Grading

Subjective papers are graded by people; objective rounds grade themselves at submit
(`grade_exam`). A submitted subjective round is `under_review` until graded.

1. **Assign** (admin) — the Assign Grading page lists papers under review. Each is assigned to an
   examiner or an admin (`AssignGradingForm`), or unassigned. `assigned_to`, `assigned_by` and
   `assigned_at` record it.
2. **My Tasks** (examiner or admin) — the papers assigned to the viewer and still under review,
   oldest submission first. The examiner dashboard previews the first five with a count of the
   rest.
3. **Grade** — the grading page shows the task, the repository, pull request and test IDs, and the
   marks available. `grade_an_exam` validates the mark (`GradeForm`: 0 up to the question's
   marks) and saves it on the paper's question row and on the booking, with `maximum_marks`
   snapshotted, the feedback, `graded_by` and `graded_at`; the booking becomes `graded`.
   `_paper_for_grading` is the one rule for both viewing and saving: assigned to the viewer and
   still under review, otherwise a 404. The save locks the row, so a double submit grades once.
4. **Grading History** — what the viewer has graded, newest first, marks shown as "12/15".
   Read-only: there is no regrade yet.

## Candidate Center

Admin-only, never examiners: it is the one place a booking reference turns back into a person.

- **Candidate Info** (`home`) — search by name, email, login id, phone or booking reference,
  25 per page; a page per candidate with their profile links and every booking.
- **Book Exam** (`book_exam_admin`) — the candidate booking picker plus a candidate box (email or
  login id). The candidate's booking rules apply in full. `booked_by` records the admin; a
  candidate's own booking has `booked_by` = the candidate, and the system-created subjective round
  has none.
- **Cancel Exam** — two steps, `cancel_exam_admin_search` then `cancel_exam_admin_confirm`. The
  search is exact only (email or login id ignoring case, or a booking reference — the 8-character
  short ref or the full ID), since a cancel cannot be undone, and lists only bookings an admin can
  still cancel. The confirm page requires a reason of 20–200 characters (`CancelBookingForm`).
  Admins may cancel until `ADMIN_CANCEL_CUTOFF_MINUTES` (5) before the start, later than
  candidates (10); `ExamBooking.admin_can_cancel` is the rule, checked again under a row lock on
  submit. Every cancellation, the candidate's own included, records `cancelled_by` and
  `cancelled_at`; an admin's also stores `cancellation_reason`, shown to admins on the candidate
  page and never to the candidate, whose My Assessments list says only "Cancelled by TestMu AI
  Admin". A candidate's detail page links straight to the confirm step for each booking that can
  still be cancelled.
- **Export Candidates** (`home`) — a CSV, one row per candidate or one per booking. Filters: one
  exam or all, and an exam date (From alone is that day; From–To includes both), read in
  Asia/Kolkata. For candidates the filters apply to the same booking, and with none every
  candidate is listed, including those who never booked. Columns are chosen as checkboxes from the
  fixed lists in `apps/home/exports.py` (email always; email and exam for bookings). Every time is
  IST, a missing value is "-", values that could run as a spreadsheet formula are escaped, and the
  file is streamed. No rows means a message, not an empty file.

Emailing the candidate about an admin's booking or cancellation waits for SMTP.

## Certificates

**One `Certificate` per passed exam** — `certificate_id` (a random UUID, which is what a public
verification link will carry), `issued_at`, `expires_at` and a one-to-one link to the exam's
**first booking** (the objective round of a two-round exam, otherwise its one booking). No PDF is
stored: it is generated from the row and the template whenever it is needed.

- **Expiry** is `issued_at` + `CERTIFICATE_VALIDITY_YEARS` (2), stored at issuance and never
  recalculated — changing the setting affects only certificates issued afterwards. 29 February
  becomes 28 February.
- **Pass or fail is decided on the whole exam**, never a round alone:
  `marks obtained across all rounds ≥ passing_marks`. Each round stores what its paper was out of
  (`maximum_marks` — objective at submit, subjective when graded), and when the exam's result is
  final `ExamBooking.freeze_passing_marks()` stores
  `ceil(total × exam.pass_percentage / 100)` on the first booking. Frozen, so a later change to an
  exam's pass percentage never re-judges old results. A weak objective round can still pass on
  the combined total, and a perfect one can still fail.
- **Get Certificate** (on the booking page) posts to `get_certificate`: not graded yet, not
  passed, or passed — then it issues the certificate once and emails it (`certificate_generated`,
  Results mailer), or re-sends it if asked again.
- **The PDF** is drawn by `apps/exam/certificates.py` with **ReportLab** (+ `svglib` for the vector
  logo and signature) — pure Python, no system libraries, the same on every OS — and attached to
  the `certificate_generated` email as `TestMu-AI-certificate-<id>.pdf`. Generated every time it
  is sent, never stored. Rubik is embedded from `static/certificates/fonts/` (Light, Regular and
  Medium, cut from Google's variable font; OFL licence alongside), so it never needs the internet.
- **The design** is TestMu AI's Figma certificate, also kept as `templates/certificates/certificate.html`
  — the same measurements in HTML/CSS, for previewing in a browser. The PDF is not made from it:
  change one and you must change the other. The logo, seal and signature are the Figma originals
  in `static/certificates/`. It prints the full UUID and "Valid until".
  Not yet built: the public verification page.

## Email

Views never send mail. They call one function, after the change it reports:

```python
from .emails import queue_email
queue_email("booking_confirmed", booking, actor=request.user)
```

which records an `OutboundEmail` row and sends it **right after the transaction commits** — never
for a change that rolled back. If that send fails, the scheduled job retries it.

```
apps/exam/emails/
  __init__.py   queue_email()   — the only thing views import
  registry.py   EVENTS          — each email: mailer, templates, dedupe key, calendar invite, skip rule
  context.py    build_context() — what templates receive: times as text in the candidate's zone, absolute links
  sender.py     send_pending()  — the only code that talks to SMTP; records the outcome
  jobs.py       the email steps of run_scheduled_jobs
templates/emails/<event>/       subject.txt · body.txt · body.html (extends emails/_base.html)
```

**The emails:** booking confirmed and booked by an admin (with the `.ics`), instant exam started
(with a live "Open the exam" link — joining is open the moment it's sent), rescheduled (updated
`.ics`), cancelled by the candidate or an admin (an `.ics` that removes the event; never the
admin's reason), reminders 60 and 30 minutes before, second round open, booking expired.

**Mailers** (`settings.MAILERS`) — one sending address (`DEFAULT_FROM_EMAIL`), replies to the same
company address (`EMAIL_REPLY_TO`), never no-reply. Each kind of email has a subject prefix:
*Exam Update*, *Reminder*, *Results*, *Staff*.

**The outbox** (`OutboundEmail`) is metadata only — no bodies — so a lakh of rows is tens of MB.
Statuses: `pending` (waiting, or retrying at `next_attempt_at`), `sent`, `failed` (5 attempts at 1,
5, 15 and 30 minutes, or a refused address; kept for support), `skipped` (no longer true when its
turn came — a reminder for a cancelled booking, or one that would arrive after the start).
`detail` holds the last error or the skip reason.

**The dedupe key** — unique per row — is what stops the every-minute job sending a reminder every
minute: queueing the same email twice returns the existing row. It includes the scheduled time
where that matters, so a rescheduled booking gets fresh reminders.

**Calendar invites** carry `ExamBooking.calendar_sequence`, raised on every reschedule and cancel,
so the candidate's calendar moves or removes the event it already has. The `.ics` download uses
the same number.

**Locally**, everything goes to **Mailpit** (`docker compose`; inbox at http://localhost:8025) —
nothing is delivered. Production points `EMAIL_HOST` at Gmail in `.env`; no code changes. On the
PythonAnywhere demo, `EMAIL_SEND_TO_ACTOR=True` sends each email to the person whose action caused
it (the subject says whose email it really was), so reviewers see what their clicks trigger and
nobody else is emailed.

## Three rules to know before writing anything

**1. Timezone conversion happens in one place.** `apps/exam/timezones.py` owns every
conversion between a candidate's wall-clock choice and the stored UTC instant. Times are stored
UTC and displayed in the zone the candidate booked in, always with the offset labelled. A
candidate who misreads their booking time misses their exam, and it is unrecoverable.

**2. The client is display only.** The date picker disables past days and caps the horizon; Join
exam greys out outside the join window; the subjective Submit stays disabled until all three links
are valid. All of these are explanations, not enforcement — a form post can be made directly, and
an Alpine binding never applies at all if the CDN script fails to load. Every rule that must hold
of a stored row is re-checked server-side.

**3. A pre-converted datetime does not survive a template filter.** With `USE_TZ = True`, Django's
`date` filter converts aware datetimes to `settings.TIME_ZONE` — UTC — before formatting, silently
undoing any conversion done in Python. Render the raw field inside `{% timezone %}` instead. See
[`docs/conventions.md`](docs/conventions.md#timezones).

`docs/conventions.md` also sets out the four places a rule can live — database constraint, model
`clean()`, form `clean()`, view check — and which to reach for. Constraints are the only real
guarantee; `bulk_create` bypasses `save()`.

## Booking model

**Self-scheduled, not slot-based.** Candidates pick their own date and time — or press **Start
Instant Exam** beside the exam picker, which books the chosen exam for *now* and goes straight to
its T&C page (`start_instant_exam`, POST only, `InstantBookingForm`). An instant booking follows
every rule below except the one-day-ahead minimum, gets its own email (`instant_booking`, no
calendar invite), and can't be rescheduled or cancelled — the cutoff has passed. There are no
pre-defined slots and no capacity, so there is no seat contention.

**Every booking route shares one copy of each rule** — `open_booking_error`, `check_clash`,
`first_round_type` and `clean_timezone_name` at the top of `apps/exam/forms.py`, used by `/book`,
Start Instant Exam, reschedule and the admin's Book Exam. Rules live in `settings.py`:

- `BOOKING_MIN_DAYS_AHEAD = 1` — no same-day booking
- `BOOKING_MAX_MONTHS_AHEAD = 3`
- `BOOKING_GAP_MINUTES = 60` — clear time required either side of an exam a candidate has
  already booked. An objective exam occupies its full duration; a subjective one is a
  36-hour window with a deadline, so it only blocks around its start.
- `BOOKING_CHANGE_CUTOFF_MINUTES = 10` — Reschedule and Cancel close this long before the start.
  `ExamBooking.can_change` is the one rule: it disables the buttons and the reschedule and cancel
  views refuse on it. A paper can only be begun from the start time, so a started paper can never
  be moved or cancelled out from under itself.
- `ADMIN_CANCEL_CUTOFF_MINUTES = 5` — the admin's cancel cutoff; see Candidate Center.

A candidate may hold only one open booking per exam **and round**, enforced by a partial unique
index (`one_open_booking_per_exam`, over candidate, exam and `round_type`). It counts `booked`,
`under_review` and `attended` rows; a graded attempt frees the exam for a retake. `BookingForm.clean()`
checks the same rule first, so a second booking is an error on the page rather than a crash; the
admin booking view also catches the `IntegrityError` for the race the form cannot see (a
double-click).

**Status means attendance; the sheet means completion.** "I'm ready to begin" marks the booking
`attended` (in `_start_or_resume`, in the same transaction that draws the paper) — the candidate
turned up. Whether they *finished* is `ExamSheet.submitted_at`. So `attended` covers papers finished,
in progress and abandoned alike, and `save_answer` and `submit_exam` treat `attended` as the state
of a live paper. A submitted **subjective** round then moves to `under_review` — the examiner's
queue, which the admin dashboard's "awaiting grading" count reads — while an objective round stays
`attended`, graded at submit. `attended()` lists all of `attended`, `under_review` and `graded`. From begin on, Reschedule and Cancel are closed for good and the booking leaves
Upcoming and the dashboard; a candidate who drops out returns through the reminder email's link to
the T&C page, which accepts an `attended` booking with an unsubmitted paper and resumes it.

**When an exam ends, its booking is released.** An objective-only exam is `graded` the moment it
is submitted. A two-round exam is one exam in two parts, so round one stays `attended` — holding
the exam — until round two ends: when round two is graded, both become `graded`; when round two is
missed, round two becomes `no_show` and round one is `cancelled` by the system (`cancelled_by`
empty) with the reason *"Cancellation due to no attempt on 2nd round"* — there is no pass or fail,
the exam simply didn't happen. Either way the candidate can book the exam again. (Migration 0020
brought existing rows into line.)

**The one thing the stored status still misses is a miss.** A booking nobody began stays `booked`
after its window has closed. `ExamBookingQuerySet` (`ExamBooking.objects`) works the candidate's
buckets out in the database from the clock as well as the status:

| Method | Matches |
|---|---|
| `upcoming()` | `booked` and the join window not yet closed |
| `no_show()` | marked `no_show`, or still `booked` with the window closed |
| `attended()` | `attended` — begun, whether finished or not |

My Assessments uses them for Upcoming (soonest first), No show and Attended; Cancelled stays a plain
status filter, and an unknown filter in the URL is a 404. The dashboard card picks the soonest
`upcoming()` booking, so a booking stays there from before its start through its join window —
when its Join button is live — until the candidate begins.

Nothing here writes: each call reads the clock and filters, and a booking falls into a bucket
whenever someone asks. The queries start from one candidate's bookings (`candidate_id` is indexed),
so they stay cheap however large the table grows.

> **What the job fixes.** `run_scheduled_jobs` now marks missed bookings `no_show` once their window
> closes, so the stored status catches up within a minute and the candidate can rebook, and closes
> papers begun but abandoned once their time is up.

**My Assessments** labels each booking with its round — Objective in blue, Subjective in amber —
read from `round_type` rather than the exam's type, which says "both" for both rounds. An attended
booking shows Show Results (still pointing at a placeholder route; results are not in scope yet)
and a disabled Get Certificate.

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
databases, staging, and CI, and they show up in a diff.

### `run_scheduled_jobs`

Everything that happens because time passes rather than because someone clicked. Run it every
minute — cron on a server, `--loop` as an always-on task on PythonAnywhere, or by hand locally:

```bash
.venv/bin/python manage.py run_scheduled_jobs          # once
.venv/bin/python manage.py run_scheduled_jobs --loop   # every 60 seconds until stopped
```

Steps, each isolated — one failing is logged and the rest still run:

1. **Queue reminders** — 60 and 30 minutes before a booking, each only inside its own slot, never
   after the start, and never for a two-round exam's second round.
2. **Mark missed bookings** — `booked` and the join window closed (start + 45 min objective,
   + 36 h subjective) → `no_show`, and "booking expired" queued for 3 hours later. A missed second
   round also cancels round one (see Booking model).
3. **Close abandoned papers** — begun, never submitted, time up (`ExamSheet.expires_at`). An
   objective round is submitted as a timeout and graded on what autosave stored — the same
   `finish_submitted_paper` (`apps/exam/papers.py`) the Submit button runs, so an objective-only
   exam is graded and a two-round exam opens its second round; the candidate is emailed that time
   ran out and it was submitted and graded. A subjective round has nothing to grade: it is
   cancelled by the system ("Not submitted within the 36-hour window"), round one with it on a
   two-round exam, and the candidate is told they can book again.
4. **Send due emails** — pending emails whose time has come: retries and delayed sends.
5. **Clean up** — sent and skipped emails older than 90 days.

**"Due and not yet sent", never "exactly now"**: a late or skipped run delays an email rather than
losing it, and the dedupe key means no run sends one twice. Rows and bookings are claimed under
row locks, so even two overlapping runs are safe — but run it on one server. No Celery: Celery
arrives only with work that must
happen right after a request at scale — certificate generation, regrades.

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

Combined two-round results against the pass percentage ·
saving the completion page's profile links and feedback · result release and Show Results ·
credentials and public verification · results and
staff emails · the public certificate verification page · recording lockdown events · `delete_question` (routed
but stubbed) · regrading · authentication (the OIDC integration with the TestMu AI login is
deferred, which is why `ExamBooking.candidate` is nullable) · automated tests · the Tailwind
production build.

One smaller gap worth knowing: **media rows are mutable** — replacing the file on an `Image` row
would change what a past paper appears to have shown.

`TRACKER.md` holds the full list.
