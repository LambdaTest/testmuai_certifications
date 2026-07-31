/**
 * Contract for the slot calendar. Agreed up front so the component can be built against
 * fixtures before the backend exists — see ./README.md.
 *
 * Do not add fields without agreeing them; the backend will implement this shape.
 */

export type Slot = {
  id: string;
  /** ISO 8601, UTC. Display in the candidate's local timezone, always labelled. */
  startsAt: string;
  /** ISO 8601, UTC. */
  endsAt: string;
  capacity: number;
  bookedCount: number;
  /** ISO 8601, UTC. After this, the slot can no longer be booked. */
  registrationClosesAt: string;
};

/** Derived from a Slot plus the current time — not stored. */
export type SlotState =
  | 'available'
  | 'filling-up'
  | 'full'
  | 'registration-closed'
  | 'past';
