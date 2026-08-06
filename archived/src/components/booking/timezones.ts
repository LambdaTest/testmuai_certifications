import { formatInTimeZone } from "date-fns-tz";

/**
 * One well-known place per UTC offset — a standard picker list, not the full
 * 400+ IANA city set. Offsets are computed live so DST stays correct.
 */
const STANDARD_TIMEZONES = [
  "Pacific/Pago_Pago",
  "Pacific/Honolulu",
  "America/Anchorage",
  "America/Los_Angeles",
  "America/Denver",
  "America/Chicago",
  "America/New_York",
  "America/Halifax",
  "America/St_Johns",
  "America/Sao_Paulo",
  "Atlantic/South_Georgia",
  "Atlantic/Azores",
  "UTC",
  "Europe/London",
  "Europe/Berlin",
  "Europe/Athens",
  "Europe/Moscow",
  "Asia/Tehran",
  "Asia/Dubai",
  "Asia/Kabul",
  "Asia/Karachi",
  "Asia/Kolkata",
  "Asia/Kathmandu",
  "Asia/Dhaka",
  "Asia/Yangon",
  "Asia/Bangkok",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Darwin",
  "Australia/Sydney",
  "Pacific/Norfolk",
  "Pacific/Auckland",
  "Pacific/Kiritimati",
];

/** Browsers may report legacy names; map them onto the standard list. */
const TZ_ALIASES: Record<string, string> = {
  "Asia/Calcutta": "Asia/Kolkata",
  "Asia/Katmandu": "Asia/Kathmandu",
  "Asia/Rangoon": "Asia/Yangon",
};

/** "+05:30" → 330, "-04:00" → -240. For sorting zones east to west. */
function offsetMinutes(offset: string): number {
  if (offset === "Z") return 0;
  const [h = "0", m = "0"] = offset.slice(1).split(":");
  const total = Number(h) * 60 + Number(m);
  return offset.startsWith("-") ? -total : total;
}

/**
 * Compact offset label shown beside the time field: "GMT+5:30", "GMT-4", "GMT".
 * Deliberately short — the full IANA name is rendered underneath it.
 */
export function gmtLabel(timezone: string, at: Date = new Date()): string {
  const raw = formatInTimeZone(at, timezone, "xxx");
  if (raw === "Z") return "GMT";

  const sign = raw[0];
  const [h = "0", m = "00"] = raw.slice(1).split(":");
  const hours = Number(h);
  const minutes = Number(m);

  if (hours === 0 && minutes === 0) return "GMT";
  return minutes === 0 ? `GMT${sign}${hours}` : `GMT${sign}${hours}:${m}`;
}

/** "Asia/Kolkata" → "Asia/Kolkata"; "America/New_York" → "America/New York". */
export function zoneName(timezone: string): string {
  return timezone.replace(/_/g, " ");
}

/** The browser's zone, mapped through the alias table. */
export function detectTimezone(): string {
  const raw = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return TZ_ALIASES[raw] ?? raw;
}

export type TimezoneOption = {
  value: string;
  /** "GMT+5:30" */
  label: string;
  /** "Asia/Kolkata" */
  place: string;
};

/**
 * Picker options sorted west to east. `include` guarantees the candidate's own
 * zone is selectable even when it isn't one of the standard entries
 * (e.g. Asia/Manila).
 */
export function timezoneOptions(include?: string): TimezoneOption[] {
  const now = new Date();
  const values = [...STANDARD_TIMEZONES];
  if (include && !values.includes(include)) values.push(include);

  return values
    .map((tz) => ({
      value: tz,
      label: gmtLabel(tz, now),
      place: zoneName(tz),
      minutes: offsetMinutes(formatInTimeZone(now, tz, "xxx")),
    }))
    .sort((a, b) => a.minutes - b.minutes || a.value.localeCompare(b.value))
    .map(({ value, label, place }) => ({ value, label, place }));
}
