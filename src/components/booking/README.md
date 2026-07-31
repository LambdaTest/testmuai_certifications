# booking components

## `SlotCalendar` — first task, self-contained

Date-and-time picker for choosing an exam slot. Built as a **pure presentational component**:
slots in, selection out. No data fetching, no database, no auth. It can be built and tested
against fixture data before the rest of the app exists, and drops into `/book` unchanged later.

### Contract

```ts
export type Slot = {
  id: string
  startsAt: string             // ISO 8601, UTC
  endsAt: string               // ISO 8601, UTC
  capacity: number
  bookedCount: number
  registrationClosesAt: string // ISO 8601, UTC
}

export type SlotCalendarProps = {
  slots: Slot[]
  selectedSlotId: string | null
  onSelect: (slotId: string) => void
  timezone?: string            // IANA name; defaults to the browser's
}
```

Do not add data fetching to this component. If it needs something not in `Slot`, extend the type
and say so — don't reach for a hook.

### Interaction

Two steps: pick a **date**, then pick a **time** from that date's slots. Days with no available
slots must be visibly distinguishable *before* the user clicks — making someone hunt through empty
days is the main way these calendars annoy people.

### Timezone — the thing most likely to go wrong

Slots arrive in **UTC**. Display them in the **candidate's local timezone**, and **label the
timezone explicitly** next to the times ("2:00 PM IST"). Never render a bare time.

A candidate who misreads their slot time misses their exam and it is unrecoverable. Treat this as
the component's most important requirement, not a detail. Write tests that render a slot under at
least two timezones and assert the displayed string.

### Slot states

Each needs a distinct visual treatment, and the last three must not be selectable:

| State | Condition |
|---|---|
| Available | capacity remaining, registration open |
| Filling up | low remaining capacity — show how many seats are left |
| Full | `bookedCount >= capacity` |
| Registration closed | now past `registrationClosesAt` |
| Past | now past `startsAt` |

### Also required

- **Empty state** — no slots at all for this exam. This will be the common case early on, and it
  is the state most often forgotten.
- **Responsive.** People book on phones. The calendar must be usable at 360px wide.
- **Keyboard and screen-reader accessible.** Arrow-key navigation between dates, visible focus
  states, times announced with their timezone. We sell an Accessibility Testing certification —
  our own booking flow failing WCAG is not acceptable.

### Don't build a date picker from scratch

Use the shadcn `Calendar` primitive (react-day-picker underneath) and layer slot availability on
top of it. Hand-rolling date grid logic is a time sink and a bug farm.

For date maths use a single library across the codebase — `date-fns` with `date-fns-tz`, or
`Temporal` if available. Do not mix approaches, and never do timezone arithmetic by hand.

### Done when

- Renders a month of fixture slots, correct in at least two timezones, with the zone labelled
- All five slot states render distinctly; full, closed, and past cannot be selected
- Empty state renders
- Fully keyboard navigable, usable at 360px
- Unit tests cover the timezone rendering and the state logic

### Bring these to the lead rather than guessing

- How far ahead should the calendar allow browsing — one month, three, unbounded?
- Should a full slot be visible-but-disabled, or hidden entirely?
- Is there a waitlist for full slots? *(open decision — assume no for now)*

---

## Later

`/book` also needs an exam selector ("Choose an exam") above this calendar, and the booking
confirmation flow. Both are separate tasks. See
[`src/app/(candidate)/book/README.md`](../../app/(candidate)/book/README.md).
