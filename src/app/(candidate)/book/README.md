# book — slot booking

`/book` is the **entry point into this app** from the main TestMu AI site. The candidate picks a
certification from a selector, then picks a slot from a calendar.

## No path parameter, by design

The main site's catalog cards ("Enroll Now") land the candidate here. Whatever exam they clicked
is **not** part of our URL and **not** read from the auth handoff.

Why: single-select on their side isn't flexible enough. A candidate who changes their mind, or
who arrives by bookmark, must be able to choose here. So the page opens with a **"Choose an exam"**
selector listing bookable certifications, and the calendar renders once one is chosen.

Consequences worth knowing:

- **There is no URL contract with the main site.** Slugs are internal. They can restructure their
  catalog freely without breaking us.
- **The only integration with the main site is authentication.** No entitlement sync, no
  registration webhook, no catalog API. See [`docs/auth.md`](../../../../docs/auth.md).
- **Booking is enrolment.** There is no prior entitlement record. "Enroll Now" on their side is a
  marketing CTA; enrolment state is created here when a slot is booked.

### Optional: prefill from a query hint

Recommended but not required. If the main site can pass the chosen exam as `?exam=<slug>`, use it
to **prefill** the selector — the candidate who just clicked "Enroll Now" on Selenium 101 should
not have to say it twice. The selector stays fully changeable.

Rules if implemented: it is a *hint*, not identity. A missing, unknown, or stale value falls back
silently to "Choose an exam" — never a 404, never an error. Keep it a query param, not a path
segment, so it can always be ignored.

*(Nobody has confirmed how the current portal passes the exam. This is not blocking — the page
works without it.)*

## The exam selector

Not a list of every certification. An option the candidate cannot book is a support ticket.
Show only certifications that are:

- published, and have at least one slot with open registration and remaining capacity
- eligible for **this** candidate — not in a post-failure cooldown, hasn't already passed it,
  prerequisites met

That is a `src/core/certifications` query, not a `SELECT *` in the page. Render at minimum the
name and level (Beginner / Advanced) to match how the main site presents them.

## The slot calendar

- **Display in the candidate's local timezone, store UTC.** Getting this wrong makes people miss
  exams. Show the timezone explicitly next to each slot.
- Show remaining capacity, or at least a "filling up" / "full" state. Do not let someone select a
  slot that has no seats.
- Changing the selected exam resets the calendar — slots belong to a specific exam version.

## Booking a slot

- **Capacity must be enforced inside a transaction that locks the slot row.** A read-then-write in
  application code double-books the last seat when two candidates click at once.
- `UNIQUE(slot_id, candidate_id)` as a database constraint, not a check in code.
- Booking must be **idempotent** — candidates double-click, and clients retry.

## Open decisions affecting this page

- **Payment.** If there is one, it now happens *here* rather than on the main site, because
  booking is enrolment. It sits between slot selection and confirmation, and a failed payment
  must not hold a seat.
- **Cancel / reschedule window** — how close to the slot can a candidate change their mind?
- **Waitlist** when a slot is full, or just show it unavailable?
- **Retake cooldown** — feeds the eligibility filter above.
