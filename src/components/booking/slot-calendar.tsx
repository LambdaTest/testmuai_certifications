import type { Slot } from './types';

/**
 * Date-and-time picker for choosing an exam slot.
 *
 * Pure presentational component: slots in, selection out. No data fetching, no database
 * access, no auth. Build against fixtures.
 *
 * Requirements and acceptance criteria: ./README.md
 */

export type SlotCalendarProps = {
  slots: Slot[];
  selectedSlotId: string | null;
  onSelect: (slotId: string) => void;
  /** IANA timezone name. Defaults to the browser's. */
  timezone?: string;
};

export function SlotCalendar(_props: SlotCalendarProps) {
  // TODO: implement — see ./README.md
  //
  // Reminders for the parts most likely to go wrong:
  //   - Slots arrive in UTC. Display local, and always label the timezone.
  //   - Five states; full / registration-closed / past must not be selectable.
  //   - Days with no available slots must be distinguishable before clicking.
  //   - Empty state (no slots at all) is the common case early on.
  //   - Keyboard navigable, usable at 360px wide.
  //   - Use the shadcn Calendar primitive; do not hand-roll the date grid.
  return null;
}
