# TestMu AI Certifications — Master Specification

**Status:** Draft · **Owner:** Harish Rajora · **Last updated:** 31 July 2026

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

Everything from slot booking onwards:

- Slot scheduling and booking, with capacity
- Exam delivery — timed, server-authoritative, autosaving
- Grading, both automatic and manual
- Result release and notification
- Credential issuance, public verification, and revocation
- Admin dashboards for certifications, exam versions, the question bank, grading, and slots

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
| Candidate | Books a slot, sits the exam, receives results and a credential |
| Admin | Authors certifications, exam versions, and questions; manages slots; releases results |
| Grader | Scores manually-graded responses. May be a permission on Admin rather than a separate role. |
| Public | Anyone verifying a credential. No account. |

Roles are held in **our** database. The main site's login establishes identity only; it cannot
grant permissions here.

---

## 4. Candidate flow

```
Main TestMu AI site  →  existing company login  →  /book
   choose exam + slot  →  wait for slot  →  instructions  →  exam  →  submit
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
| Language | TypeScript, end to end | One language and one set of validation schemas across server and client |
| Application | Next.js, App Router | Single app covering candidate, admin, and public verification surfaces |
| Database | PostgreSQL (Neon) | Relational integrity and transactions; a wrong grade is a trust problem, not a bug |
| ORM | Drizzle | Thin over SQL, keeps Postgres features reachable |
| Validation | Zod | Shared schemas; parse at every boundary |
| UI | Tailwind, shadcn/ui, TanStack Table, react-hook-form | Standard, low-ceremony, good admin-table support |
| Background work | Workflow DevKit, Vercel Cron | No long-running process exists on our hosting |
| Cache / rate limit | Upstash Redis | Not used for job queues |
| File storage | Vercel Blob | Question media |
| Hosting | Vercel Pro, Fluid Compute, Node.js 24 | No dedicated infrastructure; traffic does not warrant it yet |

**Node.js** was chosen because the team already has the expertise. **Postgres** because the domain
is deeply relational and correctness-critical: certifications, exam versions, questions, attempts,
responses, and credentials all constrain one another, and the database should refuse to store an
impossible state.

Question type payloads vary widely, so type-specific structure is stored in `JSONB` with a
discriminator column and validated by Zod — schema flexibility without giving up relational
guarantees.

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
labelled. Slot times are the product; a timezone bug means someone misses their exam.

Full detail: [`docs/conventions.md`](conventions.md).

---

## 7. Delivery approach

The main site team will not integrate with this application until it is built. We therefore build
the complete product against a **development authentication stub** that mimics the real handoff,
and integrate at the end.

The risk is that authentication cannot be exercised until late. It is managed by:

- Keeping **all** identity handling behind one adapter, `src/lib/auth.ts`, so the swap is a
  one-file change rather than a refactor
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
| 1 | **Late start** — a candidate joining 20 minutes into a 90-minute slot: full duration, or until the slot ends? | Attempts schema, exam player | High — baked into the schema |
| 2 | **Code-execution question types** — do candidates write and run code? | Question model, grading, sandbox | High — changes the data model |
| 3 | **Payment** — is there a paid step? Booking is enrolment, so it would happen here, not on the main site | Booking flow | High |
| 4 | **Proctoring** — identity verification, webcam, lockdown browser? | Exam player, vendor selection | Medium |
| 5 | **Retake policy** — cooldown after a failure, maximum attempts | Eligibility rules | Medium |
| 6 | **No-shows** — booked but never started; does it burn an attempt? | Booking, attempts | Medium |
| 7 | **Cancel / reschedule window** | Booking | Medium |
| 8 | **Waitlist** for full slots, or unavailable? | Booking, slot calendar | Low |
| 9 | **Enterprise SSO** (SAML/SCIM) for bulk seat sales | Auth — expensive to retrofit | Low now, high if sold |

---

## 9. Module index

Each module's detailed specification lives with its code. Developers own their module's spec and
keep this row current.

| Module | Purpose | Spec | Owner | Status |
|---|---|---|---|---|
| Route structure | Page inventory, auth guards, layouts | [`docs/routes.md`](routes.md) | Lead | Drafted |
| Authentication | Handoff from the company login; session; adapter | [`docs/auth.md`](auth.md) | _TBD_ | Drafted |
| Conventions | Binding rules for the whole repo | [`docs/conventions.md`](conventions.md) | Lead | Drafted |
| Data model | Tables, constraints, migrations | [`src/db/README.md`](../src/db/README.md) | _TBD_ | Outline only |
| Certifications | Products and versioned exam blueprints | [`src/core/certifications/README.md`](../src/core/certifications/README.md) | _TBD_ | Drafted |
| Questions | Question bank, types, authoring rules | [`src/core/questions/README.md`](../src/core/questions/README.md) | _TBD_ | Drafted |
| Attempts, slots, bookings | Booking, capacity, timers, response capture | [`src/core/attempts/README.md`](../src/core/attempts/README.md) | _TBD_ | Drafted |
| Grading | Scoring, pass/fail, release, regrade | [`src/core/grading/README.md`](../src/core/grading/README.md) | _TBD_ | Drafted |
| Credentials | Issuance, verification, revocation | [`src/core/credentials/README.md`](../src/core/credentials/README.md) | _TBD_ | Drafted |
| Booking page | `/book` — exam selector and slot calendar | [`src/app/(candidate)/book/README.md`](../src/app/(candidate)/book/README.md) | _TBD_ | Drafted |
| Slot calendar | Date and time picker component | [`src/components/booking/README.md`](../src/components/booking/README.md) | _Assigned_ | In progress |
| Exam player | Timed delivery, autosave, no chrome | [`src/app/(exam)/README.md`](../src/app/(exam)/README.md) | _TBD_ | Drafted |
| Admin | Authoring, slots, grading queue, credentials | [`src/app/admin/README.md`](../src/app/admin/README.md) | _TBD_ | Drafted |
| Credential verification | Public `/verify/[id]` page | [`src/app/verify/README.md`](../src/app/verify/README.md) | _TBD_ | Drafted |
| API surface | Route handlers, cron authentication | [`src/app/api/README.md`](../src/app/api/README.md) | _TBD_ | Drafted |
| Workflows | Durable background processes | [`src/workflows/README.md`](../src/workflows/README.md) | _TBD_ | Drafted |
| Testing | Strategy and required pre-launch tests | [`tests/README.md`](../tests/README.md) | _TBD_ | Drafted |

---

## 10. Glossary

| Term | Meaning |
|---|---|
| **Certification** | The product a candidate earns — e.g. "Accessibility Testing 101" |
| **Exam version** | A specific, versioned blueprint used to test a certification. Frozen once published. |
| **Slot** | A scheduled sitting of an exam version, with capacity |
| **Booking** | A candidate's reserved seat in a slot. Booking is enrolment. |
| **Attempt** | One candidate's sitting of an exam, from start to submission |
| **Response** | A candidate's answer to one question within an attempt |
| **Release** | The admin action making computed results visible to candidates. Distinct from grading. |
| **Credential** | The credential earned by passing. Canonically a public web page, not a PDF. |
