# (candidate) — signed-in candidate portal

**Auth:** session required. Enforce it in `layout.tsx` — pages inherit it.
**Layout:** candidate nav.

Scope: everything about the candidate's *own* participation. If a screen shows data about
other people or edits the product itself, it belongs in `admin/`.

Pages: `/book`, `/dashboard`, `/dashboard/bookings/[bookingId]`,
`/dashboard/attempts/[attemptId]`, `/dashboard/credentials/[credentialId]`, `/account`.

`/book` is the **entry point from the main TestMu AI site** — its catalog cards land candidates
here. It takes no path parameter: candidates pick the exam from a selector, then a slot from a
calendar. Arriving unauthenticated must redirect to login and come *back here*, not to the
dashboard. See [`book/README.md`](book/README.md).

Slot booking must not double-book the last seat. Enforce capacity inside a transaction that
locks the slot row — never a read-then-write in application code.

`/account` lives here but serves admins too — an admin is also a user. That is intentional;
do not duplicate it under `admin/`.

The exam player is **not** here — see `(exam)/`.
