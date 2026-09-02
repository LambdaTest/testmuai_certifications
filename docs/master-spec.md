# TestMu AI Certifications — Master Specification

**Status:** Living document · **Owner:** Harish Rajora · **Last updated:** 2 September 2026

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

- Self-scheduled booking — candidates pick their own date and time
- Exam delivery — timed, server-authoritative, autosaving
- Grading, both automatic and manual
- Result release and notification
- Credential issuance, public verification, and revocation
- Admin dashboards for exams, subjects, the question bank, grading and credentials

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
| Candidate | Books an exam, sits it, receives results and a credential |
| Admin | Authors exams, subjects and questions; assigns grading; manages credentials |
| Examiner | Grades subjective submissions blind — they see an exam reference, never the candidate. |
| Public | Anyone verifying a credential. No account. |

Roles are held in **our** database. The main site's login establishes identity only; it cannot
grant permissions here.

---

## 4. Candidate flow

```
Main TestMu AI site  →  existing company login  →  /book
   choose exam + time  →  wait for it  →  instructions  →  exam  →  submit
   →  "results will be emailed"  →  [grading]  →  admin releases  →  email  →  score report
                                                                   →  credential issued
```

Two properties of this flow drive much of the design:

- **Results are released, not shown.** A score is computed at submission but withheld until an
  admin releases it — normally for a whole cohort at once. This allows a broken answer key to be
  caught before results go out, and prevents candidates learning outcomes ahead of their cohort.
- **The exam player has no navigation.** Nothing links out of an exam in progress.

---

## 5. Technology

| Layer | Choice | Rationale |
|---|---|---|
| Backend | Django 5.x | The lead is the primary developer and fluent in it; batteries included for admin, ORM and migrations |
| Database | PostgreSQL | Relational integrity and transactions; a wrong grade is a trust problem, not a bug |
| Frontend | Django templates, Tailwind, Alpine.js | Server-rendered; no build step yet, no SPA to maintain |
| Background work | Celery + Redis *(not wired up)* | Real processes, unlike the serverless constraints of the original plan |
| Hosting | AWS — EC2 or Elastic Beanstalk, RDS, ElastiCache *(not provisioned)* | Already an AWS shop; approved infrastructure avoids a procurement conversation |

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
| 1 | **Late start** — a candidate joining 20 minutes late: full duration, or until a fixed end? | Attempt schema, exam player | High — baked into the schema |
| 2 | **Code-execution question types** — do candidates write and run code? | Question model, grading, sandbox | High |
| 3 | **Objective result release timing** — instantly on submit, or after a delay that leaves room to catch a mis-keyed answer? | Grading | High |
| 4 | **Payment** — is there a paid step? Booking is enrolment, so it happens here | Booking flow | Medium |
| 5 | **Question pool size** — a paper is 20 questions; the pool needs to be several times that. Nobody is assigned to write them | Content, exam player | Medium |
| 6 | **Proctoring** — identity verification, webcam, lockdown browser | Exam player | Medium |
| 7 | **Minimum lead time in hours** — the day-based rule allows 11pm for 00:15 | Booking | Low |
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

Retakes are **out of scope**: a second attempt means a new booking. Slots and capacity were
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
| Models | Users, subjects, exams, questions, bookings, exam sheets | `apps/home/models.py`, `apps/exam/models.py` | Built |
| Booking | Selector, calendar, clash rules, reschedule, cancel | `apps/exam/` | Built |
| Calendar invites | `.ics` generation and Google links | `apps/exam/calendar.py` | Built |
| Subject Center | Create, edit and browse subjects | `apps/exam/views.py` | Built |
| Exam Center | Create and edit exams, derived marks and duration, draft/publish | `apps/exam/views.py`, `forms.py` | Built |
| Question Center | Bank, authoring with answer options and media, CSV import | `apps/exam/views.py`, `forms.py`, `imports.py` | Built — delete is routed but stubbed |
| Candidate dashboard | Upcoming exam, assessments | `templates/home/dashboard_candidate.html` | Partly — badges and profile still static |
| Admin dashboard | Sections and quick actions | `templates/home/dashboard_admin.html` | UI only, unlinked |
| Examiner dashboard | Pending evaluations, grading history | — | Designed, not built |
| Exam sheets | The frozen paper and the candidate's answers | `apps/exam/models.py` | Models built |
| Exam player | Timed delivery, autosave, resume | `templates/exam/start_exam_termsandconditions.html` | Instructions page built; player is a stub |
| Grading | Assignment, evaluation, release | — | Not started |
| Credentials | Issuance, verification, revocation | — | Not started |

## 10. Glossary

| Term | Meaning |
|---|---|
| **Subject** | A field of study — e.g. Selenium, Accessibility Testing |
| **Exam** | An assessment for a subject: type, duration, pass mark. Objective (45 min) or subjective (36 h). |
| **Booking** | A candidate's chosen date and time for an exam. Booking is enrolment. |
| **Exam sheet** | The paper one candidate sat — the questions drawn for them, in order, plus their answers. Modelled as `ExamSheet`; "attempt" is the same idea in earlier drafts. |
| **Served question** | One question as it appeared on one sheet, with that candidate's answer. Modelled as `ExamSheetQuestion`; "response" in earlier drafts. |
| **Question bank** | Every question for a subject. Questions belong to subjects, not to exams, so any exam on that subject draws from the pool. |
| **Complete Evaluation** | The examiner action that records the mark, releases the result and emails the candidate. |
| **Credential** | The credential earned by passing. Canonically a public web page, not a PDF. |
