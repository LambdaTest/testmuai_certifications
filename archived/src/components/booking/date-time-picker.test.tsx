import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { addDays, format } from "date-fns";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DateTimePicker,
  composeUtcIso,
  parseTimeInput,
} from "./date-time-picker";

afterEach(cleanup);

describe("composeUtcIso — wall clock in a timezone to the UTC instant stored", () => {
  it("converts an India wall-clock time to UTC", () => {
    // 20:00 in Kolkata (UTC+5:30) is 14:30 UTC.
    expect(composeUtcIso("2027-06-15", 20, 0, "Asia/Kolkata")).toBe(
      "2027-06-15T14:30:00.000Z"
    );
  });

  it("converts a New York summer wall-clock time to UTC (DST aware)", () => {
    // 10:30 EDT (UTC-4) is 14:30 UTC.
    expect(composeUtcIso("2027-06-15", 10, 30, "America/New_York")).toBe(
      "2027-06-15T14:30:00.000Z"
    );
  });

  it("converts a New York winter wall-clock time to UTC (EST, not EDT)", () => {
    // 10:30 EST (UTC-5) is 15:30 UTC.
    expect(composeUtcIso("2027-01-15", 10, 30, "America/New_York")).toBe(
      "2027-01-15T15:30:00.000Z"
    );
  });
});

describe("parseTimeInput — forgiving typed input, Google Calendar style", () => {
  it.each([
    ["14:35", { h: 14, m: 35 }],
    ["14", { h: 14, m: 0 }],
    ["1435", { h: 14, m: 35 }],
    ["935", { h: 9, m: 35 }],
    ["2pm", { h: 14, m: 0 }],
    ["2:37 pm", { h: 14, m: 37 }],
    ["12am", { h: 0, m: 0 }],
    ["12pm", { h: 12, m: 0 }],
    ["2:3", { h: 2, m: 30 }],
    ["14.35", { h: 14, m: 35 }],
  ])("parses %s", (input, expected) => {
    expect(parseTimeInput(input)).toEqual(expected);
  });

  it.each(["24:00", "14:75", "25", "abc", "13pm", ""])(
    "rejects %s",
    (input) => {
      expect(parseTimeInput(input)).toBeNull();
    }
  );
});

describe("DateTimePicker time combobox", () => {
  it("shows the 15-minute suggestion list on focus", () => {
    render(
      <DateTimePicker selectedAt={null} onSelect={() => {}} timezone="Asia/Kolkata" />
    );
    fireEvent.focus(screen.getByRole("combobox", { name: "Time" }));
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(24 * 4);
    expect(options.some((o) => o.textContent === "09:15")).toBe(true);
  });

  it("typing shows the parsed time as a live suggestion", () => {
    render(
      <DateTimePicker selectedAt={null} onSelect={() => {}} timezone="Asia/Kolkata" />
    );
    const input = screen.getByRole("combobox", { name: "Time" });
    fireEvent.change(input, { target: { value: "2:37pm" } });
    expect(
      screen.getAllByRole("option").some((o) => o.textContent === "14:37")
    ).toBe(true);

    fireEvent.change(input, { target: { value: "14:3" } });
    expect(
      screen.getAllByRole("option").some((o) => o.textContent === "14:30")
    ).toBe(true);
  });

  it("day + picked suggestion reports the UTC instant for the timezone", () => {
    const onSelect = vi.fn();
    const { container } = render(
      <DateTimePicker selectedAt={null} onSelect={onSelect} timezone="Asia/Kolkata" />
    );

    // Pick a day ~10 days out (always inside the 3-month browse window).
    const target = addDays(new Date(), 10);
    const dayButton = container.querySelector(
      `[data-day="${target.toLocaleDateString()}"]`
    );
    expect(dayButton).not.toBeNull();
    fireEvent.click(dayButton!);

    const input = screen.getByRole("combobox", { name: "Time" });
    fireEvent.change(input, { target: { value: "2:37pm" } });
    const option = screen
      .getAllByRole("option")
      .find((o) => o.textContent === "14:37");
    fireEvent.mouseDown(option!);

    const dayKey = format(target, "yyyy-MM-dd");
    expect(onSelect).toHaveBeenLastCalledWith(
      composeUtcIso(dayKey, 14, 37, "Asia/Kolkata")
    );
  });

  it("reports nothing until a date is picked", () => {
    const onSelect = vi.fn();
    render(
      <DateTimePicker selectedAt={null} onSelect={onSelect} timezone="Asia/Kolkata" />
    );
    const input = screen.getByRole("combobox", { name: "Time" });
    fireEvent.change(input, { target: { value: "10:00" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSelect).toHaveBeenLastCalledWith(null);
  });
});
