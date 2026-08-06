# core/grading

Scoring and pass/fail determination. **Server-side only, always.** There is no scenario in which
the client scores anything.

This module is why `core/` is framework-agnostic: it must be unit testable in isolation, because
a wrong grade is a trust problem, not a bug. Aim for exhaustive coverage here before anywhere
else.

## Grade, then release — they are separate

| Timestamp | Meaning |
|---|---|
| `submitted_at` | Candidate finished |
| `graded_at` | Score computed |
| `result_released_at` | Candidate is allowed to see it |

Scoring can complete instantly and still not be visible. The gap gives you a window to catch a
broken answer key **before** results go out rather than after.

**Results are emailed on release, never on submit.** The submitted page says "results will be
emailed" and shows no score.

### Release policy

Because booking is self-scheduled there are **no cohorts** — candidates sit at different times, so
there is no batch to release together. Options:

- **Fixed delay after submission** (e.g. 24 hours) — recommended. Preserves the "results emailed
  later" experience, keeps the answer-key safety window, and needs no admin action.
- **On grading** — immediate; loses the safety window.
- **Manual per attempt** — most control, does not scale.

Currently undecided. Whichever is chosen, release must be a distinct, audited step.

## Auto vs manual

Objective types (single-select, multi-select, true/false) grade automatically on submit. Short
answer — and code execution, if that decision lands — route to the manual queue at
`/admin/grading`. An attempt is not fully graded until every response has a score.

## Rules

- Score against the **frozen exam version** the attempt referenced, never the current one.
- Persist the breakdown per response and per section, not just a total. The score report and any
  dispute both need it.
- Pass/fail uses the exam version's pass mark **as it was at publish time**.
- Grading is **idempotent and re-runnable**.
- Never mutate responses while grading. Write scores alongside them.

## Regrade

Assume you will need it. An incorrect answer key on a question used across hundreds of attempts is
a matter of when, not if. Regrade must be explicit and audited — recording who ran it, why, which
attempts changed, and especially which pass/fail outcomes flipped, since those candidates need
notifying and their credentials issuing or revoking.
