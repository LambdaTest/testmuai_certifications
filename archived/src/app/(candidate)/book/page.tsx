"use client";

// /book — entry point from the main site. Choose an exam, then pick a date
// and an exact time (candidate's own choice, no fixed slots).
// No auth or DB yet: the page owns all state and hands plain props to
// DateTimePicker, so wiring the real booking API later touches this file only.

import * as React from "react";
import { formatInTimeZone } from "date-fns-tz";
import { ArrowRight, CheckCircle2 } from "lucide-react";

import { DateTimePicker, EXAMS } from "@/components/booking";
import { detectTimezone, gmtLabel } from "@/components/booking/timezones";
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
  const [examSlug, setExamSlug] = React.useState<string | null>(() => {
    // Optional prefill hint from the main site (?exam=<slug>) — see book/README.
    // A missing or unknown value silently falls back to "choose an exam".
    const hint = new URLSearchParams(window.location.search).get("exam");
    return EXAMS.some((e) => e.slug === hint) ? hint : null;
  });
  const [timezone, setTimezone] = React.useState(detectTimezone);
  const [selectedAt, setSelectedAt] = React.useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [bookedAt, setBookedAt] = React.useState<string | null>(null);

  const exam = EXAMS.find((e) => e.slug === examSlug) ?? null;
  const examItems = EXAMS.map((e) => ({ label: e.name, value: e.slug }));

  const describe = (isoUtc: string) =>
    `${formatInTimeZone(isoUtc, timezone, "EEEE, MMMM d · HH:mm")} ${gmtLabel(
      timezone,
      new Date(isoUtc)
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
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-center">
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
          </div>

          {exam ? (
            <>
              <Separator />
              {/* Keyed on the exam only. Including the timezone here would
                  remount on every zone change and wipe the chosen date. */}
              <DateTimePicker
                key={exam.slug}
                selectedAt={selectedAt}
                onSelect={setSelectedAt}
                timezone={timezone}
                onTimezoneChange={setTimezone}
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
