import { describe, it } from 'vitest';

/**
 * Acceptance criteria from ./README.md. Fill these in as the component is built.
 */

describe('SlotCalendar', () => {
  describe('timezone rendering', () => {
    it.todo('renders slot times in the given timezone');
    it.todo('labels the timezone next to every time');
    it.todo('shows the same slot on the correct calendar day across two timezones');
  });

  describe('slot states', () => {
    it.todo('marks a slot full when bookedCount >= capacity');
    it.todo('marks a slot registration-closed after registrationClosesAt');
    it.todo('marks a slot past after startsAt');
    it.todo('shows remaining seats when capacity is nearly used');
    it.todo('does not call onSelect for full, closed, or past slots');
  });

  describe('selection', () => {
    it.todo('calls onSelect with the slot id when an available slot is chosen');
    it.todo('reflects selectedSlotId in the rendered output');
  });

  describe('empty and edge states', () => {
    it.todo('renders an empty state when there are no slots');
    it.todo('distinguishes days with no available slots');
  });

  describe('accessibility', () => {
    it.todo('supports arrow-key navigation between dates');
    it.todo('exposes times to screen readers with their timezone');
  });
});
