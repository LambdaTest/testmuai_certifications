"use client";

import * as React from "react";
import { format, parse, startOfDay, startOfMonth } from "date-fns";
import { formatInTimeZone } from "date-fns-tz";
import { CalendarOff, Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Calendar } from "@/components/ui/calendar";
import { cn } from "@/lib/utils";
import type { Slot, SlotCalendarProps, SlotStatus } from "./types";

/** Seats left at or below this count show the "filling up" warning. */
const FILLING_THRESHOLD = 5;

export function getSlotStatus(slot: Slot, now: Date = new Date()): SlotStatus {
  if (now >= new Date(slot.startsAt)) return "past";
  if (now >= new Date(slot.registrationClosesAt)) return "closed";
  if (slot.bookedCount >= slot.capacity) return "full";
  if (slot.capacity - slot.bookedCount <= FILLING_THRESHOLD) return "filling";
  return "available";
}

const SELECTABLE: ReadonlySet<SlotStatus> = new Set(["available", "filling"]);

const DAY_KEY = "yyyy-MM-dd";

/** The calendar-square date a slot falls on, in the display timezone. */
function slotDayKey(slot: Slot, timezone: string): string {
  return formatInTimeZone(slot.startsAt, timezone, DAY_KEY);
}

function timeRange(slot: Slot, timezone: string): string {
  const start = formatInTimeZone(slot.startsAt, timezone, "h:mm a");
  const end = formatInTimeZone(slot.endsAt, timezone, "h:mm a");
  return `${start} – ${end}`;
}

/** Short zone label ("IST", "EDT", "GMT+5:30") — every time must carry one. */
function zoneLabel(timezone: string, at: Date | string = new Date()): string {
  return formatInTimeZone(at, timezone, "zzz");
}

function browserTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/**
 * Pure date-and-time picker for exam slots: slots in, selected slot id out.
 * No fetching, no auth, no globals — see README in this folder for the contract.
 */
export function SlotCalendar({
  slots,
  selectedSlotId,
  onSelect,
  timezone,
}: SlotCalendarProps) {
  const tz = timezone ?? browserTimezone();
  const now = new Date();
  const today = startOfDay(now);

  const byDay = React.useMemo(() => {
    const map = new Map<string, Slot[]>();
    for (const slot of slots) {
      const key = slotDayKey(slot, tz);
      const list = map.get(key) ?? [];
      list.push(slot);
      map.set(key, list);
    }
    for (const list of map.values()) {
      list.sort((a, b) => a.startsAt.localeCompare(b.startsAt));
    }
    return map;
  }, [slots, tz]);

  const openDayKeys = React.useMemo(() => {
    const keys = new Set<string>();
    for (const [key, list] of byDay) {
      if (list.some((s) => SELECTABLE.has(getSlotStatus(s, now)))) keys.add(key);
    }
    return keys;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [byDay]);

  const firstOpenDay = React.useMemo(() => {
    const sorted = [...openDayKeys].sort();
    return sorted[0] ? parse(sorted[0], DAY_KEY, new Date()) : undefined;
  }, [openDayKeys]);

  const [selectedDay, setSelectedDay] = React.useState<Date | undefined>(firstOpenDay);
  const [month, setMonth] = React.useState<Date>(startOfMonth(firstOpenDay ?? today));

  // New exam → new slot list → jump to its first bookable day. Done by
  // adjusting state during render (React's documented pattern for reacting
  // to prop changes) rather than in an effect.
  const [prevSlots, setPrevSlots] = React.useState(slots);
  if (prevSlots !== slots) {
    setPrevSlots(slots);
    setSelectedDay(firstOpenDay);
    setMonth(startOfMonth(firstOpenDay ?? today));
  }

  if (slots.length === 0) {
    return (
      <div
        className="flex flex-col items-center gap-3 rounded-xl border border-dashed p-10 text-center"
        role="status"
      >
        <CalendarOff className="size-8 text-muted-foreground" aria-hidden />
        <p className="font-medium">No slots are open for this exam yet</p>
        <p className="max-w-sm text-sm text-muted-foreground">
          New dates are added regularly — check back soon, or pick a different
          certification for now.
        </p>
      </div>
    );
  }

  const selectedDayKey = selectedDay ? format(selectedDay, DAY_KEY) : null;
  const daySlots = selectedDayKey ? (byDay.get(selectedDayKey) ?? []) : [];
  const zone = zoneLabel(tz, now);

  return (
    <div className="flex flex-col gap-6 md:flex-row md:items-start">
      <div className="flex flex-col items-center gap-3 md:items-start">
        <Calendar
          mode="single"
          selected={selectedDay}
          onSelect={setSelectedDay}
          month={month}
          onMonthChange={setMonth}
          startMonth={startOfMonth(today)}
          endMonth={browseLimitMonth(today)}
          disabled={(date) =>
            date < today || !byDay.has(format(date, DAY_KEY))
          }
          modifiers={{
            open: (date) => openDayKeys.has(format(date, DAY_KEY)),
          }}
          modifiersClassNames={{
            open: "relative after:pointer-events-none after:absolute after:bottom-1 after:left-1/2 after:z-20 after:size-1 after:-translate-x-1/2 after:rounded-full after:bg-brand after:content-['']",
          }}
          className="rounded-2xl border bg-card p-3 shadow-sm [--cell-size:--spacing(9)] sm:[--cell-size:--spacing(10)]"
        />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="size-1.5 rounded-full bg-brand" aria-hidden />
            Seats open
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-1.5 rounded-full bg-muted-foreground/40" aria-hidden />
            Nothing bookable
          </span>
        </div>
      </div>

      <div className="min-w-0 flex-1">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-base font-semibold tracking-tight">
            {selectedDay
              ? formatInTimeZone(selectedDay, browserTimezone(), "EEEE, MMMM d")
              : "Pick a date"}
          </h3>
          <span className="text-xs text-muted-foreground">
            Times in {zone} ({tz.replace(/_/g, " ")})
          </span>
        </div>

        {daySlots.length === 0 ? (
          <p className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
            {selectedDay
              ? "No slots on this day — pick a day with a dot under it."
              : "Choose a highlighted day to see its times."}
          </p>
        ) : (
          <div
            role="radiogroup"
            aria-label={`Available times, shown in ${zone}`}
            className="flex max-h-80 flex-col gap-2 overflow-y-auto overscroll-contain pr-1 md:max-h-[26rem]"
          >
            {daySlots.map((slot) => (
              <SlotOption
                key={slot.id}
                slot={slot}
                timezone={tz}
                zone={zone}
                selected={slot.id === selectedSlotId}
                onSelect={onSelect}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function browseLimitMonth(from: Date): Date {
  const d = new Date(from);
  d.setMonth(d.getMonth() + 3);
  return d;
}

const STATUS_TEXT: Record<SlotStatus, string> = {
  available: "seats open",
  filling: "filling up",
  full: "full",
  closed: "registration closed",
  past: "already started",
};

function SlotOption({
  slot,
  timezone,
  zone,
  selected,
  onSelect,
}: {
  slot: Slot;
  timezone: string;
  zone: string;
  selected: boolean;
  onSelect: (slotId: string) => void;
}) {
  const status = getSlotStatus(slot);
  const selectable = SELECTABLE.has(status);
  const remaining = Math.max(0, slot.capacity - slot.bookedCount);
  const range = timeRange(slot, timezone);

  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      aria-label={`${range} ${zone}, ${STATUS_TEXT[status]}${selectable ? `, ${remaining} seats left` : ""}`}
      disabled={!selectable}
      onClick={() => selectable && onSelect(slot.id)}
      className={cn(
        "flex w-full items-center justify-between gap-3 rounded-xl border bg-card px-4 py-3.5 text-left text-sm transition-colors",
        "focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
        selectable && !selected && "hover:border-foreground/40 hover:bg-muted/40",
        selected && "border-zinc-200 bg-[#E7E6DF] text-zinc-900",
        !selectable && "cursor-not-allowed opacity-60"
      )}
    >
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className={cn("font-medium tabular-nums", status === "past" && "line-through")}>
          {range}{" "}
          <span
            className={cn(
              "font-normal",
              selected ? "text-zinc-500" : "text-muted-foreground"
            )}
          >
            {zone}
          </span>
        </span>
        {/* Always rendered so every card is the same height. */}
        <span
          className={cn(
            "flex items-center gap-1 text-xs",
            selected ? "text-zinc-500" : "text-muted-foreground"
          )}
        >
          <Users className="size-3" aria-hidden />
          {remaining} of {slot.capacity} seats left
        </span>
      </span>
      <StatusBadge status={status} remaining={remaining} selected={selected} />
    </button>
  );
}

function StatusBadge({
  status,
  remaining,
  selected = false,
}: {
  status: SlotStatus;
  remaining: number;
  selected?: boolean;
}) {
  switch (status) {
    case "available":
      return (
        <Badge
          variant="secondary"
          className={cn(
            "shrink-0",
            selected && "bg-zinc-900/10 text-zinc-900"
          )}
        >
          Open
        </Badge>
      );
    case "filling":
      return (
        <Badge
          className={cn(
            "shrink-0 border-transparent bg-brand/10 text-brand",
            selected && "bg-brand text-brand-foreground"
          )}
        >
          Filling fast · {remaining} left
        </Badge>
      );
    case "full":
      return (
        <Badge variant="destructive" className="shrink-0">
          Full
        </Badge>
      );
    case "closed":
      return (
        <Badge variant="outline" className="shrink-0">
          Registration closed
        </Badge>
      );
    case "past":
      return (
        <Badge variant="outline" className="shrink-0">
          Past
        </Badge>
      );
  }
}
