# booking components

## `DateTimePicker`

Date and free time-of-day picker for `/book`. The candidate picks a day on the calendar and
types or selects any time; the component reports a single **UTC instant** upward.

**Self-scheduled, not slot-based.** There are no pre-defined slots to choose from and no
capacity — the candidate chooses when they sit.

### Contract

```ts
export type DateTimePickerProps = {
  /** Chosen instant as UTC ISO, or null while incomplete. */
  selectedAt: string | null;
  onSelect: (isoUtc: string | null) => void;
  /** IANA timezone name; defaults to the browser's. */
  timezone?: string;
};
```

Pure presentational: no data fetching, no database, no auth.

### Timezone

All conversion goes through `composeUtcIso` — *all timezone math lives there and nowhere else*.
Times are displayed in the candidate's chosen zone with the offset labelled (e.g. "GMT+5:30"),
and stored as UTC.

A candidate who misreads their booking time misses their exam, and it is unrecoverable. Tests
cover DST boundaries deliberately — New York in summer versus winter — and should stay that way.

### Scheduling limits

Currently in the component:

- **No same-day booking** — earliest selectable day is tomorrow
- **3-month horizon** — `browseLimit`

These are UI guards only. The same rules must be enforced server-side in `core/attempts`, or the
API can be called directly to bypass them.

Open: a real minimum lead time in hours (a day-based rule still allows 11pm → 00:15), and whether
bookings should be limited to an availability window rather than 24/7.

### Accessibility

Keyboard navigable, visible focus, times announced with their timezone. We sell an Accessibility
Testing certification — our own booking flow failing WCAG is not acceptable.

---

## History

`SlotCalendar` was removed in favour of this component. It implemented pre-scheduled slots with
capacity, registration deadlines, and five availability states — a model that was specced by
mistake and never matched the product. If you find references to slots, capacity, or
`registrationClosesAt` anywhere, they are stale.
