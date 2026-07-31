# Route structure

Canonical page inventory and the rules for where new routes go.

## The rule

> **A route group exists because it needs a different layout or a different auth guard.**
> Not for tidiness, not for grouping by feature.

If you are adding a page and it fits an existing group's layout and guard, put it in that
group. If it needs neither a new layout nor a new guard, it does not justify a new group.

Groups in `(parentheses)` **do not appear in the URL** — they exist purely to attach a layout.
`admin/` and `verify/` are ordinary directories because we want those segments in the URL.

## Groups

| Group | URL prefix | Auth guard | Layout |
|---|---|---|---|
| `(candidate)` | `/book`, `/dashboard/*`, `/account` | session required | Candidate nav |
| `(exam)` | `/exam/[attemptId]/*` | session + must own the attempt | **None — no nav, no links out** |
| `admin` | `/admin/*` | session + admin role | Admin sidebar |
| `verify` | `/verify/[credentialId]` | none | Minimal public, indexable |

**Authorization lives in the group `layout.tsx`**, not in individual pages. One check per group;
new pages inherit protection automatically. Middleware does a coarse first pass (is there a
session cookie at all) so unauthenticated requests never reach a function that hits the database.

## Page inventory

### Out of scope: the catalog

Browsing certifications **already exists on the main TestMu AI site** and is not rebuilt here.
There is no `(marketing)` group in this repo.

Its catalog cards ("Enroll Now") land the candidate on `/book`. The exam they clicked is
deliberately **not** carried into our routing — `/book` has no path parameter and the candidate
chooses from a selector. Their catalog is single-select, which is not flexible enough once
someone changes their mind or arrives by bookmark.

Two consequences:

- **No URL contract with the main site.** Slugs stay internal; they can restructure their catalog
  without breaking us.
- **Authentication is the only integration between the two systems.** No entitlement sync, no
  registration webhook, no catalog API. Booking *is* enrolment — see
  [`src/app/(candidate)/book/README.md`](../src/app/(candidate)/book/README.md).

An unauthenticated visitor arriving at `/book` must be sent to login and returned **there**, not
dumped on the dashboard. Preserve the return path.

### Out of scope: login

**There is no login screen in this repo.** The company's existing login handles it. Hitting the
portal unauthenticated redirects to that screen, and the candidate returns here already signed
in. We exchange the handoff for a local session and land them on their original destination.

No sign-in, sign-up, forgot-password, or password reset pages. No password hashes in our database.

Routes involved: `GET /api/auth/login`, `GET /api/auth/callback`, `POST /api/auth/logout`.
Full contract: [`auth.md`](auth.md).

### `(candidate)` — the signed-in candidate's own participation

| Route | Purpose |
|---|---|
| `/book` | **Entry point from the main site.** "Choose an exam" selector, then a slot calendar. No path parameter. |
| `/dashboard` | Upcoming booked slots, in-progress attempts, earned credentials |
| `/dashboard/bookings` | My bookings |
| `/dashboard/bookings/[bookingId]` | Booking detail — join link when the slot opens, cancel/reschedule |
| `/dashboard/attempts` | Attempt history |
| `/dashboard/attempts/[attemptId]` | Score report — per-section breakdown, pass/fail |
| `/dashboard/credentials` | Earned credentials |
| `/dashboard/credentials/[credentialId]` | Share, download, copy verification link |
| `/account` | Profile, password, email preferences — **also used by admins** |

### `(exam)` — the exam player

Its own group specifically so it renders **no navigation**. A logged-in nav bar mid-exam is an
invitation to leave, and it muddies "did the candidate navigate away" telemetry.

| Route | Purpose |
|---|---|
| `/exam/[attemptId]/instructions` | Rules, duration, attempt policy. Candidate accepts before the timer starts. |
| `/exam/[attemptId]` | The question player itself |
| `/exam/[attemptId]/submitted` | Confirmation. Results may not be immediate if manual grading is pending. |

Constraints for anyone working here:
- **The timer is server-authoritative.** `started_at` / `expires_at` live in Postgres. The
  client clock is display only; every response write and the final submit revalidate server-side.
- **Answer keys must never be in the payload.** See `docs/conventions.md`.
- Responses autosave as the candidate goes — a closed browser must not lose work.

### `admin` — the product, and other people

| Route | Purpose |
|---|---|
| `/admin` | Overview: attempts today, pending grading queue depth, pass rates |
| `/admin/slots` | Scheduled exam slots — create, set capacity, open/close registration |
| `/admin/slots/[slotId]` | Roster, attendance, and **release results for this cohort** |
| `/admin/certifications` | Certification products |
| `/admin/certifications/[certificationId]` | Product-level detail |
| `/admin/certifications/[certificationId]/versions` | Exam versions for this certification |
| `/admin/certifications/[certificationId]/versions/[versionId]` | Blueprint editor: sections, question selection, weights, pass mark |
| `/admin/questions` | Question bank — search, filter, tag |
| `/admin/questions/[questionId]` | Question editor |
| `/admin/questions/import` | Bulk import |
| `/admin/attempts` | All attempts, filterable |
| `/admin/attempts/[attemptId]` | Attempt inspector + full audit trail — this is the dispute-resolution screen |
| `/admin/grading` | Manual grading queue for subjective / code answers |
| `/admin/grading/[responseId]` | Grade a single response |
| `/admin/credentials` | Issued credentials, revocation |
| `/admin/candidates` | Candidate records |
| `/admin/candidates/[candidateId]` | Single candidate: attempts, credentials, support actions |
| `/admin/settings` | Org settings, email templates |
| `/admin/settings/users` | Admin users and roles |

### `verify` — public credential verification

| Route | Purpose |
|---|---|
| `/verify/[credentialId]` | **The canonical credential.** Public, indexable, revocable. |

This page, not a PDF, is the real credential. It must render correctly for an anonymous visitor
with no account, must clearly show revoked/expired states, and should carry Open Graph tags so
it previews well when shared to LinkedIn.

## "Common" — three different things

Requests for "a shared page" are usually one of these. Identify which before creating anything:

1. **Common routes** — `/login`, `/account`. Real routes serving multiple audiences. They live
   in whichever group's layout and guard fit; `/account` sits under `(candidate)` because an
   admin is also a user.
2. **Common chrome** — not a route problem. `src/app/layout.tsx` is the root layout (html, fonts,
   providers). Every group layout nests inside it.
3. **Common UI** — not a route problem either. `src/components/`. Most "shared" instincts land here.

## API routes

See `src/app/api/README.md`. Route handlers stay thin: parse, authorize, call `src/core`, respond.
