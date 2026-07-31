# core/grading

Scoring and pass/fail determination. **Server-side only, always.** There is no scenario in which
the client scores anything.

This module is the reason `core/` is framework-agnostic: it must be unit testable in isolation,
because a wrong grade is a trust problem, not a bug. Aim for exhaustive test coverage here before
anywhere else.

## Grade, then release — they are separate

| Timestamp | Meaning |
|---|---|
| `submitted_at` | Candidate finished |
| `graded_at` | Score computed |
| `result_released_at` | Candidate is allowed to see it |

Scoring can complete instantly and still not be visible. That separation buys two things: batch
release per slot, so nobody in a cohort learns their result before the others; and a window to
catch a broken answer key **before** results go out rather than after.

**Results are emailed on release, never on submit.** The submitted page says "results will be
emailed" and shows no score.

## Auto vs manual

Objective types (single-select, multi-select, true/false) grade automatically on submit. Short
answer — and code execution, if that decision lands — route to the manual queue at
`/admin/grading`. An attempt is not fully graded until every response has a score.

## Rules

- Score against the **frozen exam version** the attempt referenced, never the current one.
- Persist the score breakdown per response and per section, not just a total. The candidate's
  score report and any dispute both need it.
- Pass/fail is computed from the exam version's pass mark **as it was at publish time**.
- Grading is **idempotent and re-runnable**. If an answer key is found to be wrong, you must be
  able to regrade affected attempts and record that it happened.
- Never mutate the attempt's responses while grading. Write scores alongside them.

## Regrade

Assume you will need it. An incorrect answer key on a question used across hundreds of attempts is
a matter of when, not if. Regrade must be an explicit, audited operation that records who ran it,
why, and which attempts changed — including attempts whose pass/fail outcome flipped, since those
candidates need notifying.
