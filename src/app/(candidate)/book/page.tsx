"use client";

// /book — entry point from the main site. Choose an exam, then pick a date
// and an exact time (candidate's own choice, no fixed slots).
// No auth or DB yet: the page owns all state and hands plain props to
// DateTimePicker, so wiring the real booking API later touches this file only.

import * as React from "react";
import { formatInTimeZone } from "date-fns-tz";
import { ArrowRight, CheckCircle2, ChevronDown } from "lucide-react";

import { DateTimePicker, EXAMS } from "@/components/booking";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";

/** "+05:30" → 330, "-04:00" → -240. For sorting zones east to west. */
function offsetMinutes(offset: string): number {
  const [h = "0", m = "0"] = offset.slice(1).split(":");
  const total = Number(h) * 60 + Number(m);
  return offset.startsWith("-") ? -total : total;
}

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
  "Pacific/Guadalcanal",
  "Pacific/Auckland",
  "Pacific/Tongatapu",
];

/** Browsers may report legacy names; map them onto the standard list. */
const TZ_ALIASES: Record<string, string> = {
  "Asia/Calcutta": "Asia/Kolkata",
  "Asia/Katmandu": "Asia/Kathmandu",
  "Asia/Rangoon": "Asia/Yangon",
};

function standardTimezones() {
  const now = new Date();
  return STANDARD_TIMEZONES.map((tz) => {
    const offset = formatInTimeZone(now, tz, "xxx");
    return {
      value: tz,
      label: `(UTC${offset}) ${tz.replace(/_/g, " ")}`,
      minutes: offsetMinutes(offset),
    };
  }).sort((a, b) => a.minutes - b.minutes || a.value.localeCompare(b.value));
}

const emptySubscribe = () => () => {};

export default function BookPage() {
  // Everything here needs the browser (timezone detection), so render only
  // after mount to avoid SSR/client mismatch.
  const mounted = React.useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false
  );

  if (!mounted) {
    return (
      <main className="mx-auto max-w-4xl px-4 py-10">
        <div className="h-64 animate-pulse rounded-xl bg-muted" aria-hidden />
      </main>
    );
  }
  return <BookPageInner />;
}

function BookPageInner() {
  const rawBrowserTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const browserTz = TZ_ALIASES[rawBrowserTz] ?? rawBrowserTz;
  const timezones = React.useMemo(() => {
    const all = standardTimezones();
    // The detected zone should always be pickable, even when it isn't one of
    // the standard entries (e.g. Asia/Manila).
    if (!all.some((t) => t.value === browserTz)) {
      const offset = formatInTimeZone(new Date(), browserTz, "xxx");
      all.unshift({
        value: browserTz,
        label: `(UTC${offset}) ${browserTz.replace(/_/g, " ")}`,
        minutes: offsetMinutes(offset),
      });
    }
    return all;
  }, [browserTz]);

  const [examSlug, setExamSlug] = React.useState<string | null>(() => {
    // Optional prefill hint from the main site (?exam=<slug>) — see book/README.
    // A missing or unknown value silently falls back to "choose an exam".
    const hint = new URLSearchParams(window.location.search).get("exam");
    return EXAMS.some((e) => e.slug === hint) ? hint : null;
  });
  const [timezone, setTimezone] = React.useState(browserTz);
  const [selectedAt, setSelectedAt] = React.useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [bookedAt, setBookedAt] = React.useState<string | null>(null);

  const exam = EXAMS.find((e) => e.slug === examSlug) ?? null;
  const examItems = EXAMS.map((e) => ({ label: e.name, value: e.slug }));

  const describe = (isoUtc: string) =>
    `${formatInTimeZone(isoUtc, timezone, "EEEE, MMMM d · HH:mm")} ${formatInTimeZone(
      isoUtc,
      timezone,
      "zzz"
    )}`;

  return (
    <main className="mx-auto max-w-4xl px-4 py-10">
      <header className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-balance sm:text-4xl">
          Book Your Exam
        </h1>
      </header>

      <Card>
        <CardContent className="flex flex-col gap-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <Select
              items={examItems}
              value={examSlug}
              onValueChange={(value) => {
                setExamSlug(value as string | null);
                setSelectedAt(null); // times belong to a specific exam
                setBookedAt(null);
              }}
            >
              <SelectTrigger
                className="w-full data-[size=default]:h-11 sm:w-[26rem]"
                aria-label="Certification exam"
              >
                <SelectValue>
                  {exam ? (
                    <span className="flex items-center gap-2">
                      {exam.name}
                      <Badge variant="secondary">{exam.level}</Badge>
                    </span>
                  ) : (
                    "Choose an exam"
                  )}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {EXAMS.map((e) => (
                  <SelectItem key={e.slug} value={e.slug}>
                    <span className="flex w-full items-center justify-between gap-2">
                      {e.name}
                      <Badge variant="secondary">{e.level}</Badge>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* Native select on purpose — the OS list popup matches the
                main site's picker. */}
            <div className="relative w-full sm:ml-auto sm:w-72">
              <select
                aria-label="Display timezone"
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                className="h-8 w-full appearance-none truncate rounded-lg border border-input bg-transparent pr-8 pl-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
              >
                {timezones.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
              <ChevronDown
                className="pointer-events-none absolute top-1/2 right-2 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden
              />
            </div>
          </div>

          {exam ? (
            <>
              <Separator />
              <DateTimePicker
                key={`${exam.slug}:${timezone}`}
                selectedAt={selectedAt}
                onSelect={setSelectedAt}
                timezone={timezone}
              />
            </>
          ) : (
            <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
              Choose an exam above to see the calendar.
            </p>
          )}
        </CardContent>
      </Card>

      {exam && selectedAt && !bookedAt && (
        <Card className="mt-6 border-primary/40">
          <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="font-medium">{exam.name}</p>
              <p className="text-sm text-muted-foreground">{describe(selectedAt)}</p>
            </div>
            <Button size="lg" onClick={() => setConfirmOpen(true)}>
              Confirm booking <ArrowRight className="size-4" aria-hidden />
            </Button>
          </CardContent>
        </Card>
      )}

      {exam && bookedAt && (
        <Card className="mt-6 border-green-600/40">
          <CardContent className="flex items-start gap-3">
            <CheckCircle2 className="mt-0.5 size-5 text-green-600" aria-hidden />
            <div>
              <p className="font-medium">Booking confirmed (preview)</p>
              <p className="text-sm text-muted-foreground">
                {exam.name} — {describe(bookedAt)}. Once the backend exists this
                will create a real booking and appear in your dashboard.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm your booking</DialogTitle>
            <DialogDescription>
              {exam?.name} — {selectedAt ? describe(selectedAt) : ""}.
              Double-check the time and timezone: missing your exam cannot be
              undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>
              Go back
            </Button>
            <Button
              onClick={() => {
                setBookedAt(selectedAt);
                setConfirmOpen(false);
              }}
            >
              Confirm booking
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
