# core/attempts

Bookings and the attempt lifecycle. The most correctness-sensitive module after grading.

## Self-scheduled, not slot-based

**There are no pre-scheduled slots.** Candidates pick their own date and time. A booking is
simply `(candidate, exam version, scheduled_at)`.

This means there is **no capacity, no seat contention, and no double-booking race** — the
concurrency problem that would otherwise dominate this module does not exist. It also means
there are no cohorts, which changes how results are released (see `core/grading`).

## Booking

- A booking is `UNIQUE(candidate_id, exam_version_id)` among active bookings — one open booking
  per exam per candidate. Enforce as a partial unique index, not a check in code.
- Booking **is** enrolment. There is no prior entitlement record.
- Booking must be **idempotent** — candidates double-click and clients retry.
- Store `scheduled_at` as `timestamptz` in UTC, plus the **IANA timezone the candidate booked
  in**. Keep both: the timezone is what you show them in reminders and what you reason about
  when they claim the time was wrong.

### Scheduling rules

Currently enforced in the UI only — they belong here so the API cannot be bypassed:

| Rule | Current behaviour |
|---|---|
| No same-day booking | Earliest selectable day is tomorrow |
| Maximum horizon | 3 months ahead |
| Minimum lead time | **Open decision** — day-based only, so an 11pm booking for 00:15 is ~1 hour out |
| Availability window | **Open decision** — currently 24/7 |

## The timer is server-authoritative

`started_at` and `expires_at` live in Postgres. The countdown the candidate sees is display only.
Every response write and the final submit revalidate the deadline server-side — a tampered client
clock must not buy extra time.

**Open decision:** how late can a candidate start relative to `scheduled_at`? A grace window
(say 15 minutes) after which the booking lapses is the usual answer, but it needs deciding — it
determines whether `expires_at` is `started_at + duration` or `scheduled_at + grace + duration`.

## Freezing the served set

When an attempt starts, the exact question set — including randomised question and option order
— is **frozen and persisted**. Do not re-derive it per page load. The candidate must see a stable
exam if they refresh, and a dispute years later requires knowing precisely what was served.

Self-scheduling makes the *selection* rules matter more than they would with fixed cohorts: see
`core/questions` on drawing each attempt from a larger pool.

## Submission

- **Idempotent.** A double-click, a retry, or a duplicate auto-submit must not create a second
  submission. Guard with a state transition, not check-then-write.
- Responses **autosave** as the candidate works. A closed tab must not lose answers.
- A submitted attempt is **never mutated**. Grading writes to separate columns and rows.

## Missed and abandoned

- `/api/cron/expire-attempts` closes out attempts whose timer expired but that were never
  submitted, grading whatever was saved.
- A booking whose scheduled time passed without the candidate starting is a **no-show**.
  Whether that burns an attempt is an open decision.

## Audit trail

Every meaningful event — booked, rescheduled, started, question served, response saved,
submitted, expired, graded, released — appends to `attempt_events`. Append-only. This is what
`/admin/attempts/[id]` renders and what settles disputes.
