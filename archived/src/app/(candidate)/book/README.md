# book — exam booking

`/book` is the **entry point into this app** from the main TestMu AI site. The candidate chooses a
certification from a selector, then picks their own date and time.

## Self-scheduled

**There are no pre-defined slots.** The candidate picks any date and time within the allowed
range. No capacity, no seats, no waitlist, no registration deadline.

## No path parameter

The main site's catalog cards land the candidate here. Whatever exam they clicked is **not** part
of our routing and **not** read from the auth handoff — they choose from the selector.

- **No URL contract with the main site.** Slugs stay internal; they can restructure their catalog
  without breaking us.
- **Authentication is the only integration between the two systems.** No entitlement sync, no
  registration webhook, no catalog API.
- **Booking is enrolment.** There is no prior entitlement record.

### Optional: prefill from a query hint

The main site currently redirects with a numeric exam id (`?id=2934`, TestMu AI's own course id).
We ignore it today. If you later want it to preselect the dropdown, map it via
`certifications.external_ref` and treat it strictly as a *hint* — a missing, unknown, or stale
value falls back silently to "Choose an exam", never a 404.

## The exam selector

Not a list of every certification. An option the candidate cannot book is a support ticket. Show
only certifications that are published and that this candidate is eligible for — not in a
post-failure cooldown, hasn't already passed it, prerequisites met.

That is a `src/core/certifications` query, not a `SELECT *` in the page. Render at least the name
and level (Beginner / Advanced).

## Choosing a time

Handled by [`DateTimePicker`](../../../../components/booking/README.md). Constraints today:

- **No same-day booking** — earliest selectable day is tomorrow
- **3-month horizon**
- Displayed in the candidate's chosen timezone with the offset labelled; stored UTC

**These are UI guards only.** The same rules must be enforced in `core/attempts`, or the API can
be called directly to bypass them.

## Booking

- **Idempotent** — candidates double-click and clients retry.
- One open booking per exam per candidate, as a database constraint.
- Store both the UTC instant and the IANA timezone the candidate booked in.

## Open decisions

- **Payment.** If there is one, it sits between time selection and confirmation, and a failed
  payment must not create a booking.
- **Minimum lead time in hours** — the day-based rule still allows 11pm → 00:15.
- **Availability window** — 24/7, or restricted hours?
- **Cancel / reschedule** — allowed up to how long before the booked time?
- **Retake cooldown** — feeds the eligibility filter above.
