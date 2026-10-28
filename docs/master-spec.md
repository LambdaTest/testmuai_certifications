# TestMu AI Certifications — Master Specification

**Status:** Living document · **Owner:** Harish Rajora · **Last updated:** 27 October 2026

This is the top-level specification. It states what we are building and why, fixes the technology
and the architectural rules, and indexes every module. **Detailed specs live with their modules**
— this document links to them rather than restating them, so it stays short enough to remain
accurate.

Developers: when you start a module, write its detailed spec at the linked location and update
its row in the module index.

---

## 1. Purpose

TestMu AI sells professional certifications. Delivery is currently handled by an external vendor,
Eklavya. We are bringing it in house.

**Why:**

- **Control.** Certification content, grading rules, and the candidate experience are core to the
  product and should not sit behind a vendor's roadmap.
- **Cost.** Per-candidate vendor fees scale badly as volume grows.
- **Data.** Attempt data, pass rates, and question performance are valuable and currently not ours
  to query.
- **Trust.** A disputed result must be explainable from our own audit trail.

**Success looks like:** candidates book, sit, and pass certifications entirely on our own
platform, with results and credentials issued by us — and Eklavya switched off.

---

## 2. Scope

### In scope

Everything from booking onwards:

- Self-scheduled booking — candidates pick their own date and time, or start an exam instantly
- Exam delivery — timed, server-authoritative, autosaving; one or two rounds
- Grading, both automatic (objective) and manual (subjective, blind)
- Email — confirmations, changes, reminders and expiry, with calendar invites
- Result release and notification
- Credential issuance, public verification, and revocation
- Admin tools for exams, subjects, the question bank, grading, candidates and credentials

### Out of scope

- **The public catalog.** Browsing certifications already exists at `testmuai.com/certifications/`
  and is not rebuilt. Its cards link into our booking page.
- **Login.** The company's existing login screen authenticates candidates. This application has no
  sign-in UI and stores no passwords.

### Deferred

- **Integration with the main site.** We build the complete product against a development stub
  first, then integrate. See §7 for the risk this carries and how it is managed.
- Proctoring, enterprise SSO, and code-execution question types are open decisions (§8).

---

## 3. Users and roles

| Role | Description |
|---|---|
| Candidate | Books an exam (or starts one instantly), sits it, receives results and a credential |
| Admin | Authors exams, subjects and questions; assigns and does grading; books, cancels and exports for candidates (Candidate Center); manages credentials |
| Examiner | Grades the subjective papers assigned to them, blind — they see a booking reference, never the candidate. Own simpler layout. |
| Public | Anyone verifying a credential. No account. |

Roles are held in **our** database. The main site's login establishes identity only; it cannot
grant permissions here.

---

## 4. Candidate flow

```
Main TestMu AI site  →  existing company login  →  /book
   choose exam  →  pick a date and time  →  confirmation email + calendar invite
                      →  reminders 60 and 30 min before  →  join from the start time
             or  →  Start Instant Exam  →  booked for now
   →  instructions (T&C)  →  "I'm ready to begin"  →  exam  →  submit  →  completion page
        objective-only:  score shown on submit; exam graded
        two rounds:      objective round, then the subjective round opens 30 min later for 36 h
                         →  [examiner grades, blind]  →  exam graded
   →  [result release and credential — not built]
```

Properties of this flow that drive much of the design:

- **Joining opens at the start time, not before,** and stays open for the round's length (45
  minutes objective, 36 hours subjective). Whoever begins inside that window gets the full duration
  from the moment they begin. A booking nobody began becomes `no_show` when the window closes, and
  the candidate is emailed 3 hours later that they can book again.
- **A two-round exam is one exam in two parts.** Missing the second round cancels the whole exam —
  no pass or fail — and the candidate books both rounds again.
- **Objective scores are shown on submit**, on the completion page (decided 2026). Release of
  graded and combined results, and how a cohort's results go out, is still open (§8).
- **The exam player has no navigation.** Nothing links out of an exam in progress.

---

## 5. Technology

| Layer | Choice | Rationale |
|---|---|---|
| Backend | Django 5.x | The lead is the primary developer and fluent in it; batteries included for admin, ORM and migrations |
| Database | PostgreSQL | Relational integrity and transactions; a wrong grade is a trust problem, not a bug |
| Frontend | Django templates, Tailwind, Alpine.js | Server-rendered; no build step yet, no SPA to maintain |
| Scheduled work | `manage.py run_scheduled_jobs`, every minute — cron on a server, an always-on `--loop` task on PythonAnywhere | Reminders, missed bookings and email retries need a clock, not a broker. Celery + Redis only if heavy work after requests appears *(not wired up)* |
| Email | SMTP — Mailpit locally, Gmail (Google Workspace) in production *(waiting on IT for the App Password)* | One company address; an outbox table makes sending reliable without a queue service |
| Hosting | AWS — EC2 or Elastic Beanstalk, RDS *(not provisioned)*. A PythonAnywhere demo for reviewers is planned. | Already an AWS shop; approved infrastructure avoids a procurement conversation |

> **The project began on Next.js and TypeScript and moved to Django in August 2026**, one merged
> PR in. The reason was capacity: the lead became the primary developer, and velocity in a
> familiar stack outweighed everything else. The Next implementation is kept in `archived/` as a
> working reference for the booking UX. Data model, auth design and conventions survived the move
> unchanged — only the framework differed.

**Postgres** was chosen because the domain is deeply relational and correctness-critical: certifications, exam versions, questions, attempts,
responses, and credentials all constrain one another, and the database should refuse to store an
impossible state.

Question type payloads vary widely, so type-specific structure will be stored in `JSONB` with a
discriminator column — schema flexibility without giving up relational guarantees. This is also
why there is no SQLite fallback: it emulates JSONB as text.

---

## 6. Architecture rules

These are binding. Deviating from them is a review-blocking issue.

**Dependencies point one way: `apps.exam` never imports `apps.home`.** The exam app reaches the
user only through `settings.AUTH_USER_MODEL`, which is a string, so there is no import at all.
`apps.home` may import from `apps.exam`.

**Business logic does not require an HTTP request.** Anything that can be expressed as data in,
data out, lives in a module of plain functions — `timezones.py`, `calendar.py`, `imports.py` —
rather than inside a view. That is what lets the CSV importer serve both a web page and a
management command, and it is how the grading engine should be written when it arrives.

**Answer keys never reach the candidate.** `AnswerOptions.is_correct` is the key. It must not
appear in a context variable, a template, or a payload on any candidate-facing surface. The exam
player is the highest-risk one: it renders questions and their options to the person being tested.
Use separate read paths for candidates and for grading rather than relying on remembering to strip
a field. A leaked key invalidates every credential issued from that question.

**Served questions are immutable, and enforced structurally.** The Question Bank has no edit page
by design, so a question's wording is fixed once written. `ExamSheetQuestion.question` is
`PROTECT`, so a question that has appeared on any paper cannot be deleted — the database refuses,
not a view. Questions that were never served stay freely deletable, and anything in circulation is
withdrawn by setting `Question.status` to `retired` rather than removed.

> This replaces the earlier plan of versioning published exams. Versioning was needed because
> questions were assumed to be editable; making them immutable removes the problem rather than
> managing it, and removes the JSON snapshot per served question along with it.

**Views never send email.** They call `apps.exam.emails.queue_email(event, booking)` inside the
transaction that made the change. It records an `OutboundEmail` row and sends right after commit —
so no email for a change that rolled back, and none lost to a mail server that was briefly down
(the scheduled job retries). Bodies are rendered at send time from the booking, never stored.

**Anything that happens because time passed lives in `run_scheduled_jobs`**, not in a request:
reminders, marking missed bookings, sending due emails, cleanup. Each step is safe to repeat,
isolated from the others, and claims its rows under locks.

**Every booking route shares one copy of each booking rule.** `/book`, Start Instant Exam,
reschedule and the admin's Book Exam all call the same functions in `apps/exam/forms.py`
(`open_booking_error`, `check_clash`, `first_round_type`, `clean_timezone_name`). Two copies
would let one route accept what another refuses.

**The exam timer is server-authoritative.** `ExamSheet.expires_at` lives in Postgres; the client
countdown is display only. A deadline the browser can report is a deadline a candidate can extend.

**The client is display only, generally.** Alpine loads from a CDN, so if that request fails every
binding on the page is inert and the markup renders as-is. A disabled button, a capped date picker
and a greyed-out Publish are explanations, never enforcement. Every rule that must hold of a
stored row is re-checked server-side.

**Everything that mutates is a POST, and idempotent where possible.** Users double-click and
clients retry. `cancel_booking` filters on `status=BOOKED` in its lookup, so a second POST 404s
instead of acting twice; the import confirm clears its session key before writing, so a reload
cannot import the same file again.

**All timestamps are `timestamptz` in UTC**, converted only for display, always with the timezone
labelled. Booking times are the product; a timezone bug means someone misses their exam.

Full detail: [`docs/conventions.md`](conventions.md).

---

## 7. Delivery approach

The main site team will not integrate with this application until it is built. We therefore build
the complete product against a **development authentication stub** that mimics the real handoff,
and integrate at the end.

The risk is that authentication cannot be exercised until late. It is managed by:

- Keeping **all** identity handling behind one module so the swap is a one-file change
- Treating `users.external_id` as an **opaque string** — never parsed, never assumed numeric
- Carrying a nullable `certifications.external_ref` from the first migration, to absorb whatever
  identifier the main site eventually sends
- Obtaining the integration **specification** early — from internal records or from Eklavya. That
  is documentation, not a change request, and costs the other team nothing.

**Cutover should be per-certification, not big-bang.** Pointing a single certification at the new
platform is the smallest possible change for the main site team, limits blast radius to one exam,
and proves the system with real candidates before the rest follows.

---

## 8. Open decisions

Unresolved. Each blocks specific work; owner is the project lead unless stated.

| # | Decision | Blocks | Priority |
|---|---|---|---|
| 1 | **Combined results and release** — pass is 70% of both rounds together; how and when graded and combined results are released, and what the candidate sees | Results, credentials | High |
| 2 | **Code-execution question types** — do candidates write and run code? | Question model, grading, sandbox | High |
| 3 | **Instant exams: scope** — which exams allow Start Instant Exam (all published, today), and is the integrity risk of starting minutes after someone shares the questions acceptable until question pools are large? | Booking | High |
| 4 | **Payment** — is there a paid step? Booking is enrolment, so it happens here — and it must come before an instant start | Booking flow | Medium |
| 5 | **Question pool size** — a paper is 20 questions; the pool needs to be several times that. Nobody is assigned to write them | Content, exam player | Medium |
| 6 | **Proctoring** — identity verification, webcam, lockdown browser | Exam player | Medium |
| 7 | **Opening the instructions early** — e.g. the T&C page 5 minutes before the start, with the clock still starting at "begin" | Exam delivery | Low |
| 8 | **`role` as a single field** — an examiner cannot currently also sit an exam | Auth | Low now |

**Decided since the last revision**, and no longer open:

- **Manual question selection** is deferred, not built. The team confirmed it has never been used
  on the vendor platform, so publishing a manual exam is refused rather than half-supported.
- **Questions are immutable** — no edit page, ever. That is what lets a served question be a
  foreign key instead of a snapshot.
- **The paper is drawn at Start Test**, not at booking and not lazily as the candidate advances.
- **Options are not shuffled per candidate.** Question randomisation already does the work, and
  shuffling breaks any option that depends on its position.
- **Bulk import is CSV only.** PDF and Word have no structure to rely on; a spreadsheet converts
  to CSV for free.
- **A reload resumes, it does not cancel.** `ExamSheet.current_position` is the bookmark.
- **Late start** — joining opens at the start time and closes after the round's length; whoever
  begins inside it gets the full duration from "begin". No early start.
- **Statuses mean attendance, not results.** "I'm ready to begin" sets `attended`; a submitted
  subjective round is `under_review`; grading sets `graded`. An objective-only exam is `graded` on
  submit; a two-round exam's first round stays `attended` until the second is graded (both then
  `graded`) or missed (second `no_show`, first `cancelled` by the system with the reason
  "Cancellation due to no attempt on 2nd round"). A finished exam releases the candidate to book it
  again.
- **Changing a booking** — candidates may reschedule or cancel until 10 minutes before the start;
  admins may cancel until 5 minutes before, with a reason the candidate never sees.
- **Email** — one company address, replies welcome (never no-reply); subject prefixes
  *Exam Update*, *Reminder*, *Results*, *Staff*; no reminders for a second round.
- **Instant start** — a candidate may start an exam now, skipping the calendar; same rules as any
  booking except the one-day-ahead minimum. Booking for later *today* is not offered.

Retakes are a new booking, allowed once the previous attempt has finished. Slots and capacity were
removed from the design — booking is self-scheduled.

A fuller list of deferred work lives in `TRACKER.md`, which is local-only.

## 9. Module index

Each module's detailed specification lives with its code. Developers own their module's spec and
keep this row current.

| Area | Purpose | Where | Status |
|---|---|---|---|
| Routes | URL inventory and the rules for new ones | [`routes.md`](routes.md) | Current |
| Authentication | Handoff from the TestMu AI login | [`auth.md`](auth.md) | Current, not built |
| Conventions | Binding rules for the repo | [`conventions.md`](conventions.md) | Current |
| Models | Users, subjects, exams, questions, bookings, exam sheets, outbound email | `apps/home/models.py`, `apps/exam/models.py` | Built |
| Booking | Selector, calendar, clash rules, reschedule, cancel, Start Instant Exam | `apps/exam/views.py`, `forms.py` | Built |
| Calendar invites | `.ics` generation (with sequence for updates) and Google links | `apps/exam/calendar.py` | Built |
| Subject Center | Create, edit and browse subjects | `apps/exam/views.py` | Built |
| Exam Center | Create and edit exams, derived marks and duration, draft/publish | `apps/exam/views.py`, `forms.py` | Built |
| Question Center | Bank, authoring with answer options and media, CSV import | `apps/exam/views.py`, `forms.py`, `imports.py` | Built — delete is routed but stubbed |
| Candidate dashboard | Next exam, My Assessments by bucket | `apps/home/views.py`, `templates/home/` | Built — badges and profile still static |
| Admin dashboard | Counts and the accordion sidebar | `templates/home/dashboard_admin.html`, `base_staff.html` | Partly — tiles and some sidebar items still unlinked |
| Exam player | T&C, timed objective player with autosave and resume, subjective round, submit, completion page | `apps/exam/views.py`, `templates/exam/` | Built |
| Grading | Assign, My Tasks, blind grading page, Grading History | `apps/exam/views.py`, `templates/exam/` | Built — regrade and result release not started |
| Examiner area | Own layout and dashboard (pending preview), My Tasks, Grading History | `templates/base_examiner.html`, `home/dashboard_examiner.html` | Built |
| Candidate Center | Candidate Info, Book Exam, Cancel Exam, Export Candidates | `apps/home/` and `apps/exam/views.py` | Built |
| Email | Outbox, nine email types, reminders, retries, Mailpit locally | `apps/exam/emails/`, `templates/emails/` | Built — production sending waits on IT |
| Scheduled work | Reminders, missed bookings, sending, cleanup | `apps/exam/management/commands/run_scheduled_jobs.py`, `sweeps.py` | Built — closing abandoned papers is next |
| Credentials | Issuance, verification, revocation | — | Not started |

## 10. Glossary

| Term | Meaning |
|---|---|
| **Subject** | A field of study — e.g. Selenium, Accessibility Testing |
| **Exam** | An assessment for a subject: type, duration, pass mark. Objective (45 min), subjective (36 h), or both — two rounds. |
| **Round** | One sitting of an exam. A two-round exam is two bookings: the objective round, then the subjective round the system books 30 minutes after it is submitted. |
| **Booking** | A candidate's chosen date and time for one round. Booking is enrolment. |
| **Instant exam** | A booking made for *now* from Start Instant Exam, going straight to the instructions. |
| **Join window** | From a booking's start time until the round's length after it — when it can be begun. |
| **Exam sheet** | The paper one candidate sat — the questions drawn for them, in order, plus their answers. Modelled as `ExamSheet`; "attempt" is the same idea in earlier drafts. |
| **Served question** | One question as it appeared on one sheet, with that candidate's answer. Modelled as `ExamSheetQuestion`; "response" in earlier drafts. |
| **Question bank** | Every question for a subject. Questions belong to subjects, not to exams, so any exam on that subject draws from the pool. |
| **Grading** | An admin assigns a submitted subjective paper; the assignee grades it blind from My Tasks. Release to the candidate is not built. |
| **Outbox** | `OutboundEmail` — every email sent or due, with its status. The record behind "I never got my email". |
| **Mailer** | A kind of email (exam, reminders, results, staff): its sender name and subject prefix. |
| **Credential** | The credential earned by passing. Canonically a public web page, not a PDF. |
