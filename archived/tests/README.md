# tests

## Where to put the effort

Coverage is not uniform here. Ranked by consequence of being wrong:

1. **`core/grading`** — a wrong grade is a trust and possibly legal problem, not a bug. Aim for
   exhaustive coverage: every question type, partial credit, pass-mark boundaries, unanswered
   questions, regrade idempotency.
2. **`core/attempts`** — timer expiry, late start, double-submit, concurrent booking against the
   last seat. Concurrency bugs here are invisible until they hit production on a full slot.
3. **`core/credentials`** — issuance idempotency, revoked and expired states rendering correctly.
4. Everything else.

`core/` is framework-agnostic precisely so these run as fast unit tests with no HTTP and no
Next.js. That is the point of the dependency rule.

## Tests that must exist before launch

- **No answer key appears in any candidate-facing payload.** Assert it against the actual
  response shapes, for every question type. This is the defect class that invalidates
  credentials — a review checklist is not sufficient.
- **A revoked credential never renders as valid** on the public verification page.
- **Capacity cannot be exceeded** under concurrent booking.
- **A tampered client clock cannot extend an attempt.**

## Setup

- Vitest. Unit tests need no database; integration tests run against a real Postgres (a Neon
  branch, not a mock — the constraints being tested are database constraints).
- The dev auth stub makes end-to-end flows testable before the main-site integration exists.
- Workflow integration tests use `@workflow/vitest`; keep them in a separate config from unit tests.
