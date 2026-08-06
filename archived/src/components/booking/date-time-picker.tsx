"use client";

import * as React from "react";
import { addDays, format, startOfDay, startOfMonth } from "date-fns";
import { formatInTimeZone, fromZonedTime } from "date-fns-tz";
import { ChevronDown, Clock } from "lucide-react";

import { gmtLabel, timezoneOptions, zoneName } from "./timezones";

import { Calendar } from "@/components/ui/calendar";
import { cn } from "@/lib/utils";

export type DateTimePickerProps = {
  /** Chosen instant as UTC ISO, or null while incomplete. */
  selectedAt: string | null;
  onSelect: (isoUtc: string | null) => void;
  /** IANA timezone name; defaults to the browser's. */
  timezone?: string;
  /**
   * When provided, the offset shown beside the time becomes a picker. Omit to
   * render it as static text.
   */
  onTimezoneChange?: (timezone: string) => void;
};

type Time = { h: number; m: number };

const pad = (n: number) => String(n).padStart(2, "0");
const fmtTime = (t: Time) => `${pad(t.h)}:${pad(t.m)}`;

/** Google-Calendar-style suggestion grid: every 15 minutes, 00:00 → 23:45. */
const SUGGESTIONS: Time[] = Array.from({ length: 24 * 4 }, (_, i) => ({
  h: Math.floor(i / 4),
  m: (i % 4) * 15,
}));

/**
 * Forgiving parser for typed times, Google Calendar style.
 * Accepts "14", "14:35", "1435", "935", "2pm", "2:37 pm", "14.35", "2:3" (→ 2:30).
 */
export function parseTimeInput(raw: string): Time | null {
  let s = raw.trim().toLowerCase().replace(/\s+/g, "").replace(/\./g, ":");
  if (!s) return null;

  let meridiem: "am" | "pm" | null = null;
  const merMatch = s.match(/(am|pm|a|p)$/);
  if (merMatch) {
    meridiem = merMatch[1]!.startsWith("a") ? "am" : "pm";
    s = s.slice(0, -merMatch[1]!.length);
  }
  if (!/^\d{1,4}(:\d{0,2})?$/.test(s)) return null;

  let h: number;
  let m: number;
  if (s.includes(":")) {
    const [hs = "", ms = ""] = s.split(":");
    h = Number(hs);
    // A single minute digit means tens: "2:3" → 2:30, like Google.
    m = ms === "" ? 0 : ms.length === 1 ? Number(ms) * 10 : Number(ms);
  } else if (s.length <= 2) {
    h = Number(s);
    m = 0;
  } else {
    h = Number(s.slice(0, -2));
    m = Number(s.slice(-2));
  }

  if (meridiem) {
    if (h < 1 || h > 12) return null;
    if (h === 12) h = meridiem === "am" ? 0 : 12;
    else if (meridiem === "pm") h += 12;
  }

  if (!Number.isInteger(h) || h < 0 || h > 23) return null;
  if (!Number.isInteger(m) || m < 0 || m > 59) return null;
  return { h, m };
}

/** "14:30" and "1430" both match a typed "14:3" / "143". */
const norm = (s: string) => s.replace(":", "").replace(/^0/, "");

/**
 * The candidate's wall-clock choice ("2027-06-15", 20, 0) in `tz`, as the UTC
 * instant to store. All timezone math lives here — nowhere else.
 */
export function composeUtcIso(
  dayKey: string,
  hour: number,
  minute: number,
  tz: string
): string {
  return fromZonedTime(
    `${dayKey}T${pad(hour)}:${pad(minute)}:00`,
    tz
  ).toISOString();
}

function browserTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

function browseLimit(from: Date): Date {
  const d = new Date(from);
  d.setMonth(d.getMonth() + 3);
  return d;
}

/**
 * Date + free time-of-day picker: the candidate picks a day on the calendar
 * and types or picks any time (Google Calendar-style combobox). Reports a
 * single UTC instant upward. Pure UI — no fetching, no auth.
 */
export function DateTimePicker({
  selectedAt,
  onSelect,
  timezone,
  onTimezoneChange,
}: DateTimePickerProps) {
  const tz = timezone ?? browserTimezone();
  const now = new Date();
  const today = startOfDay(now);
  // Same-day booking is not allowed — the earliest pickable day is tomorrow.
  const earliestDay = addDays(today, 1);

  const [day, setDay] = React.useState<Date | undefined>(undefined);
  const [time, setTime] = React.useState<Time>({ h: 9, m: 0 });
  const [month, setMonth] = React.useState<Date>(startOfMonth(today));

  const emit = (d: Date | undefined, t: Time) => {
    onSelect(d ? composeUtcIso(format(d, "yyyy-MM-dd"), t.h, t.m, tz) : null);
  };

  const zone = gmtLabel(tz, now);
  const tzOptions = timezoneOptions(tz);

  return (
    <div className="flex flex-col gap-6 md:flex-row md:items-start">
      <Calendar
        mode="single"
        selected={day}
        onSelect={(d) => {
          setDay(d);
          emit(d, time);
        }}
        month={month}
        onMonthChange={setMonth}
        startMonth={startOfMonth(today)}
        endMonth={browseLimit(today)}
        disabled={{ before: earliestDay, after: browseLimit(today) }}
        className="rounded-2xl border bg-card p-3 shadow-sm [--cell-size:--spacing(9)] sm:[--cell-size:--spacing(10)]"
      />

      <div className="min-w-0 flex-1">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-base font-semibold tracking-tight">
            {day ? format(day, "EEEE, MMMM d") : "Pick a date"}
          </h3>
        </div>

        <div
          className={cn(
            "rounded-xl border bg-card p-4",
            !day && "pointer-events-none opacity-50"
          )}
        >
          <p className="mb-3 flex items-center gap-1.5 text-sm font-medium">
            <Clock className="size-4 text-muted-foreground" aria-hidden />
            Choose your time
          </p>
          <div className="flex items-start gap-2">
            <TimeCombobox
              value={time}
              onCommit={(t) => {
                setTime(t);
                emit(day, t);
              }}
            />

            {onTimezoneChange ? (
              <div className="min-w-0">
                {/* A real <select> for keyboard and screen-reader behaviour,
                    laid transparently over the trigger so the closed state can
                    show just the offset while the list stays readable. */}
                <div className="relative inline-flex">
                  <select
                    aria-label="Timezone"
                    value={tz}
                    onChange={(e) => {
                      const next = e.target.value;
                      onTimezoneChange(next);
                      // Keep the wall-clock the candidate chose and re-resolve
                      // it in the new zone, the way calendar apps do — picking
                      // a zone means "I meant 4:30 *there*", not "shift my time".
                      if (day) {
                        onSelect(
                          composeUtcIso(
                            format(day, "yyyy-MM-dd"),
                            time.h,
                            time.m,
                            next
                          )
                        );
                      }
                    }}
                    className="peer absolute inset-0 w-full cursor-pointer opacity-0"
                  >
                    {tzOptions.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.label} · {t.place}
                      </option>
                    ))}
                  </select>
                  <span
                    aria-hidden
                    className="pointer-events-none inline-flex h-9 items-center gap-1 rounded-md border border-input px-2 text-sm whitespace-nowrap peer-focus-visible:border-ring peer-focus-visible:ring-3 peer-focus-visible:ring-ring/50 dark:bg-input/30"
                  >
                    {zone}
                    <ChevronDown
                      className="size-3.5 text-muted-foreground"
                      aria-hidden
                    />
                  </span>
                </div>
                <p className="mt-1 truncate pl-0.5 text-xs text-muted-foreground">
                  {zoneName(tz)}
                </p>
              </div>
            ) : (
              <span className="mt-2 text-sm text-muted-foreground">{zone}</span>
            )}
          </div>

          {day && selectedAt && (
            <p className="mt-4 rounded-lg bg-[#E7E6DF] px-3 py-2 text-sm font-medium text-zinc-900">
              {formatInTimeZone(selectedAt, tz, "EEEE, MMMM d · HH:mm")}{" "}
              <span className="font-normal text-zinc-500">{zone}</span>
            </p>
          )}
        </div>

        {!day && (
          <p className="mt-3 text-xs text-muted-foreground">
            Select a date on the calendar first, then set the exact time that
            suits you.
          </p>
        )}
      </div>
    </div>
  );
}

/**
 * Google Calendar-style time field: click for a scrollable list of 15-minute
 * suggestions; type anything ("2:37pm", "14:3") and the parsed time appears
 * as the top suggestion, live.
 */
function TimeCombobox({
  value,
  onCommit,
}: {
  value: Time;
  onCommit: (t: Time) => void;
}) {
  const [text, setText] = React.useState(fmtTime(value));
  const [open, setOpen] = React.useState(false);
  const [typed, setTyped] = React.useState(false);
  const [active, setActive] = React.useState(0);
  const listRef = React.useRef<HTMLUListElement>(null);

  // Full list when just opened; filtered (parsed candidate first) once typing.
  const items = React.useMemo(() => {
    if (!typed) return SUGGESTIONS;
    const matches = SUGGESTIONS.filter((t) =>
      norm(fmtTime(t)).startsWith(norm(text.trim()))
    );
    const parsed = parseTimeInput(text);
    if (parsed && !matches.some((t) => t.h === parsed.h && t.m === parsed.m)) {
      return [parsed, ...matches];
    }
    return matches;
  }, [text, typed]);

  const openList = () => {
    setOpen(true);
    setTyped(false);
    setText(fmtTime(value));
    const idx = SUGGESTIONS.findIndex(
      (t) => t.h === value.h && (t.m === value.m || t.m > value.m - 15)
    );
    setActive(Math.max(0, idx));
  };

  React.useEffect(() => {
    if (!open) return;
    listRef.current
      ?.querySelector('[data-active="true"]')
      ?.scrollIntoView?.({ block: "nearest" });
  }, [open, active]);

  const commit = (t: Time) => {
    setText(fmtTime(t));
    setTyped(false);
    setOpen(false);
    onCommit(t);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      setOpen(false);
      setText(fmtTime(value));
      return;
    }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) return openList();
      const delta = e.key === "ArrowDown" ? 1 : -1;
      setActive((a) => Math.min(items.length - 1, Math.max(0, a + delta)));
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      const pick = items[active] ?? parseTimeInput(text);
      if (pick) commit(pick);
      return;
    }
  };

  return (
    <div className="relative">
      <input
        type="text"
        role="combobox"
        aria-label="Time"
        aria-expanded={open}
        aria-controls="time-suggestions"
        autoComplete="off"
        spellCheck={false}
        value={text}
        onFocus={(e) => {
          openList();
          // Select the current value so typing replaces it, like Google.
          e.currentTarget.select();
        }}
        onClick={() => !open && openList()}
        onChange={(e) => {
          setText(e.target.value);
          setTyped(true);
          setOpen(true);
          setActive(0);
        }}
        onBlur={() => {
          setOpen(false);
          const parsed = parseTimeInput(text);
          if (parsed && fmtTime(parsed) !== fmtTime(value)) commit(parsed);
          else setText(fmtTime(value));
        }}
        onKeyDown={onKeyDown}
        className="h-9 w-24 rounded-lg border border-input bg-transparent px-2.5 text-sm tabular-nums outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
      />
      {open && items.length > 0 && (
        <ul
          id="time-suggestions"
          role="listbox"
          ref={listRef}
          className="absolute z-50 mt-1 max-h-56 w-28 overflow-y-auto rounded-lg border bg-popover py-1 shadow-md"
        >
          {items.map((t, i) => (
            <li
              key={fmtTime(t)}
              role="option"
              aria-selected={i === active}
              data-active={i === active}
              // onMouseDown so selection wins over the input's blur.
              onMouseDown={(e) => {
                e.preventDefault();
                commit(t);
              }}
              onMouseEnter={() => setActive(i)}
              className={cn(
                "cursor-pointer px-3 py-1.5 text-sm tabular-nums",
                i === active && "bg-accent text-accent-foreground"
              )}
            >
              {fmtTime(t)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
