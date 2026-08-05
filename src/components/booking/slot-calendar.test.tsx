import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SlotCalendar, getSlotStatus } from "./slot-calendar";
import type { Slot } from "./types";

afterEach(cleanup);

// Far-future fixed date so nothing here depends on when the tests run.
// 14:30 UTC = 20:00 in India (UTC+5:30) = 10:30 EDT in New York (DST).
const slot = (over: Partial<Slot> = {}): Slot => ({
  id: "s1",
  startsAt: "2027-06-15T14:30:00.000Z",
  endsAt: "2027-06-15T15:30:00.000Z",
  capacity: 30,
  bookedCount: 10,
  registrationClosesAt: "2027-06-15T12:30:00.000Z",
  ...over,
});

describe("getSlotStatus", () => {
  const now = new Date("2027-06-01T00:00:00Z");

  it("is available with seats and open registration", () => {
    expect(getSlotStatus(slot(), now)).toBe("available");
  });

  it("is filling when few seats remain", () => {
    expect(getSlotStatus(slot({ bookedCount: 27 }), now)).toBe("filling");
  });

  it("is full when booked meets capacity", () => {
    expect(getSlotStatus(slot({ bookedCount: 30 }), now)).toBe("full");
  });

  it("is closed after registration deadline even with seats free", () => {
    expect(
      getSlotStatus(slot(), new Date("2027-06-15T13:00:00Z"))
    ).toBe("closed");
  });

  it("is past once the slot has started", () => {
    expect(
      getSlotStatus(slot(), new Date("2027-06-15T14:30:00Z"))
    ).toBe("past");
  });
});

describe("SlotCalendar timezone rendering", () => {
  // The README calls this the component's most important requirement: the same
  // UTC instant must render as different, explicitly-labelled local times.

  it("renders the slot time in India time with the zone labelled", () => {
    render(
      <SlotCalendar
        slots={[slot()]}
        selectedSlotId={null}
        onSelect={() => {}}
        timezone="Asia/Kolkata"
      />
    );
    const option = screen.getByRole("radio");
    expect(option).toHaveTextContent(/8:00\s*PM/);
    expect(option).toHaveTextContent(/GMT\+0?5:30|IST/);
  });

  it("renders the same slot in New York time with the zone labelled", () => {
    render(
      <SlotCalendar
        slots={[slot()]}
        selectedSlotId={null}
        onSelect={() => {}}
        timezone="America/New_York"
      />
    );
    const option = screen.getByRole("radio");
    expect(option).toHaveTextContent(/10:30\s*AM/);
    expect(option).toHaveTextContent(/EDT/);
  });
});

describe("SlotCalendar selection rules", () => {
  it("reports the slot id when an open slot is clicked", () => {
    const onSelect = vi.fn();
    render(
      <SlotCalendar
        slots={[slot()]}
        selectedSlotId={null}
        onSelect={onSelect}
        timezone="Asia/Kolkata"
      />
    );
    fireEvent.click(screen.getByRole("radio"));
    expect(onSelect).toHaveBeenCalledWith("s1");
  });

  it("full slots are visible but not clickable", () => {
    const onSelect = vi.fn();
    render(
      <SlotCalendar
        slots={[
          slot({ id: "open" }),
          slot({ id: "full", startsAt: "2027-06-15T16:00:00.000Z", endsAt: "2027-06-15T17:00:00.000Z", bookedCount: 30 }),
        ]}
        selectedSlotId={null}
        onSelect={onSelect}
        timezone="Asia/Kolkata"
      />
    );
    const fullOption = screen
      .getAllByRole("radio")
      .find((el) => el.textContent?.includes("Full"));
    expect(fullOption).toBeDisabled();
    fireEvent.click(fullOption!);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("shows remaining seats on open slots", () => {
    render(
      <SlotCalendar
        slots={[slot({ bookedCount: 26 })]}
        selectedSlotId={null}
        onSelect={() => {}}
        timezone="Asia/Kolkata"
      />
    );
    expect(screen.getByText(/4 of 30 seats left/)).toBeInTheDocument();
  });
});

describe("SlotCalendar empty state", () => {
  it("renders a friendly message when there are no slots at all", () => {
    render(
      <SlotCalendar slots={[]} selectedSlotId={null} onSelect={() => {}} />
    );
    expect(
      screen.getByText(/no slots are open for this exam yet/i)
    ).toBeInTheDocument();
  });
});
