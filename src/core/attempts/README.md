# core/attempts

Slots, bookings, and the attempt lifecycle. The most correctness-sensitive module after grading.

## Slots and bookings

- A **slot** is a scheduled sitting of a specific exam version: start, end, timezone, capacity,
  registration deadline.
- A **booking** is a candidate's seat in a slot. `UNIQUE(slot_id, candidate_id)`.
- An **attempt** hangs off a booking. Booking is enrolment — there is no prior entitlement record.

**Capacity must be enforced inside a transaction that locks the slot row.** A read-then-write in
application code double-books the last seat when two candidates click simultaneously. This is the
single most likely concurrency bug in the product.

## The timer is server-authoritative

`started_at` and `expires_at` live in Postgres. The countdown the candidate sees is display only.
Every response write and the final submit revalidate the deadline server-side — a tampered client
clock must not buy extra time.

**Open decision:** a candidate joining 20 minutes into a 90-minute slot — do they get the full 90
minutes, or only until the slot ends? This determines whether `expires_at` is `started_at +
duration` or `slot.ends_at`. Decide before building; it is painful to retrofit.

## Freezing the served set

When an attempt starts, the exact question set — including any randomisation of question or
option order — is **frozen and persisted**. Do not re-derive it on each page load. Two reasons:
the candidate must see a stable exam if they refresh, and a dispute years later requires knowing
precisely what was served.

## Submission

- **Idempotent.** A double-click, a retry, or a duplicate cron-driven auto-submit must not create
  a second submission. Guard with a state transition, not a check-then-write.
- Responses **autosave** as the candidate works. A closed tab must not lose answers.
- A submitted attempt is **never mutated**. Grading writes to separate columns and rows.

## Abandoned attempts

`/api/cron/expire-attempts` closes out attempts whose timer expired but that were never submitted
— browser closed, connection dropped. They are graded on whatever was saved. No-show handling
(booked, never started) is an open decision.

## Audit trail

Every meaningful event — started, question served, response saved, submitted, expired, graded,
released — appends to `attempt_events`. Append-only. This is what `/admin/attempts/[id]` renders
and what settles disputes.
