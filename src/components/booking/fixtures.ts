// Fixture data so the booking UI can be built and demoed before the database,
// auth, or any API exists. The /book page swaps this for a real fetch later —
// the SlotCalendar component itself never knows the difference.

import { addDays, addMonths, set } from "date-fns";
import type { Slot } from "./types";

export type ExamLevel = "Beginner" | "Advanced";

export type Exam = {
  slug: string;
  name: string;
  level: ExamLevel;
};

// Mirrors exam_subjects.tsv. Real list comes from src/core/certifications later.
export const EXAMS: Exam[] = [
  { slug: "selenium-101", name: "Selenium 101", level: "Beginner" },
  { slug: "testng", name: "TestNG", level: "Beginner" },
  { slug: "selenium-advanced", name: "Selenium Advanced", level: "Advanced" },
  { slug: "junit", name: "JUnit", level: "Beginner" },
  { slug: "selenium-java-101", name: "Selenium Java 101", level: "Beginner" },
  { slug: "selenium-c-sharp-101", name: "Selenium C# 101", level: "Beginner" },
  { slug: "selenium-javascript-101", name: "Selenium JavaScript 101", level: "Beginner" },
  { slug: "selenium-python-101", name: "Selenium Python 101", level: "Beginner" },
  { slug: "cypress-101", name: "Cypress 101", level: "Beginner" },
  { slug: "selenium-ruby-101", name: "Selenium Ruby 101", level: "Beginner" },
  { slug: "playwright-101", name: "Selenium Playwright 101", level: "Beginner" },
  { slug: "playwright-102", name: "Playwright 102 with HyperExecute", level: "Advanced" },
  { slug: "manual-testing", name: "Manual Testing", level: "Beginner" },
  { slug: "automation-testing", name: "Automation Testing", level: "Advanced" },
  { slug: "hyperexecute", name: "HyperExecute", level: "Advanced" },
  { slug: "appium-101", name: "Appium 101", level: "Beginner" },
  { slug: "espresso-101", name: "Espresso 101", level: "Beginner" },
  { slug: "kaneai", name: "KaneAI", level: "Advanced" },
  { slug: "accessibility-testing-101", name: "Accessibility Testing", level: "Beginner" },
  { slug: "visual-testing-agent", name: "Visual Testing Agent", level: "Advanced" },
  { slug: "ai-testing", name: "AI Testing", level: "Advanced" },
  { slug: "kane-cli", name: "KaneCLI", level: "Advanced" },
];

// Cheap deterministic hash so every render of the fixtures looks the same —
// no Math.random, or the demo would change on every reload.
function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i += 1) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h;
}

const START_HOURS_UTC = [5, 7, 9, 11, 13, 15, 17];
const CAPACITY = 30;

/**
 * Generates ~6 weeks of slots per exam around `now`, deliberately covering all
 * five states: a few past days, one closed-registration slot, some full, some
 * nearly full ("filling"), the rest open. One exam gets no slots at all so the
 * empty state can be seen (pick "KaneCLI" in the selector).
 */
export function makeFixtureSlots(now: Date = new Date()): Record<string, Slot[]> {
  const bySlug: Record<string, Slot[]> = {};

  for (const exam of EXAMS) {
    if (exam.slug === "kane-cli") {
      bySlug[exam.slug] = [];
      continue;
    }

    const slots: Slot[] = [];
    for (let day = -4; day <= 45; day += 1) {
      const dayHash = hash(`${exam.slug}:${day}`);
      // Roughly 55% of days have slots; which weekdays varies by exam.
      if (dayHash % 9 < 4) continue;

      const date = addDays(now, day);
      for (const hour of START_HOURS_UTC) {
        const slotHash = hash(`${exam.slug}:${day}:${hour}`);
        if (slotHash % 3 === 0 && hour !== 13) continue; // not every time every day

        const startsAt = set(date, { hours: hour, minutes: 0, seconds: 0, milliseconds: 0 });
        const endsAt = set(date, { hours: hour + 1, minutes: 0, seconds: 0, milliseconds: 0 });

        // Mix of fill levels: ~1 in 6 full, ~1 in 5 nearly full, rest open.
        let bookedCount: number;
        if (slotHash % 6 === 0) bookedCount = CAPACITY;
        else if (slotHash % 5 === 0) bookedCount = CAPACITY - 1 - (slotHash % 3);
        else bookedCount = slotHash % (CAPACITY - 8);

        // Registration normally closes 2h before start; a few future slots are
        // already closed so that state is visible in the demo.
        const closesEarly = slotHash % 11 === 0 && day > 0;
        const registrationClosesAt = closesEarly
          ? new Date(now.getTime() - 60 * 60 * 1000)
          : new Date(startsAt.getTime() - 2 * 60 * 60 * 1000);

        slots.push({
          id: `${exam.slug}-${startsAt.toISOString()}`,
          startsAt: startsAt.toISOString(),
          endsAt: endsAt.toISOString(),
          capacity: CAPACITY,
          bookedCount,
          registrationClosesAt: registrationClosesAt.toISOString(),
        });
      }
    }
    bySlug[exam.slug] = slots;
  }

  return bySlug;
}

/** Calendar browsing is capped this far ahead. Open question for the lead. */
export function browseLimit(now: Date = new Date()): Date {
  return addMonths(now, 3);
}
