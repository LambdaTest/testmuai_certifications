# TestMu AI Certifications — Master Specification

**Status:** Living document · **Owner:** Harish Rajora · **Last updated:** 19 August 2026

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

**Dependencies point one way: `app/ → core/ → db/`.** `core/` contains all business logic and may
not import React, `next/*`, or anything from `app/`. This keeps the grading engine unit-testable
without HTTP, and leaves open the option of lifting `core/` into a standalone service later.

**Answer keys never reach the client.** Not in a prop, a payload, a serialised server component,
or a source map. Candidate-facing and grading-facing read models are separate types, so the
mistake is a compile error rather than a leak. A leaked key invalidates every credential issued
from that question.

**Published exam versions are immutable.** Edits create a new version. A candidate disputing a
result years later must see the exam exactly as it was served.

**The exam timer is server-authoritative.** Deadlines live in Postgres; the client countdown is
display only.

**No long-running processes, no module-level state.** Our hosting is serverless. Anything
outliving a request is a durable workflow or a cron route. Everything that mutates is idempotent.

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
| 5 | **Question pool size** — self-scheduling lets candidates share questions, so each paper must draw from a much larger pool | Content, exam player | Medium |
| 6 | **Proctoring** — identity verification, webcam, lockdown browser | Exam player | Medium |
| 7 | **Minimum lead time in hours** — the day-based rule allows 11pm for 00:15 | Booking | Low |
| 8 | **`role` as a single field** — an examiner cannot currently also sit an exam | Auth | Low now |

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
| Models | Users, subjects, exams, questions, bookings | `apps/home/models.py`, `apps/exam/models.py` | Built |
| Booking | Selector, calendar, clash rules, reschedule, cancel | `apps/exam/` | Built |
| Calendar invites | `.ics` generation and Google links | `apps/exam/calendar.py` | Built |
| Candidate dashboard | Upcoming exam, assessments | `templates/home/dashboard_candidate.html` | Partly — badges and profile still static |
| Admin dashboard | Sections and quick actions | `templates/home/dashboard_admin.html` | UI only, unlinked |
| Examiner dashboard | Pending evaluations, grading history | — | Designed, not built |
| Attempts and exam player | Timed delivery, autosave | — | Not started |
| Grading | Assignment, evaluation, release | — | Not started |
| Credentials | Issuance, verification, revocation | — | Not started |

## 10. Glossary

| Term | Meaning |
|---|---|
| **Subject** | A field of study — e.g. Selenium, Accessibility Testing |
| **Exam** | An assessment for a subject: type, duration, pass mark. Objective (45 min) or subjective (36 h). |
| **Booking** | A candidate's chosen date and time for an exam. Booking is enrolment. |
| **Attempt** | One candidate's sitting of an exam, from start to submission |
| **Response** | A candidate's answer to one question within an attempt |
| **Complete Evaluation** | The examiner action that records the mark, releases the result and emails the candidate. |
| **Credential** | The credential earned by passing. Canonically a public web page, not a PDF. |
