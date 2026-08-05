// Contract from src/components/booking/README.md — do not change shape without
// updating the README and telling the backend owner. All timestamps are ISO 8601, UTC.

export type Slot = {
  id: string;
  startsAt: string;
  endsAt: string;
  capacity: number;
  bookedCount: number;
  registrationClosesAt: string;
};

export type SlotCalendarProps = {
  slots: Slot[];
  selectedSlotId: string | null;
  onSelect: (slotId: string) => void;
  /** IANA timezone name; defaults to the browser's. */
  timezone?: string;
};

/** The five visual states from the README. Only the first two are selectable. */
export type SlotStatus = "available" | "filling" | "full" | "closed" | "past";
