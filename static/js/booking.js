/**
 * Booking page behaviour.
 *
 * Display only. The wall-clock choice (date, hour, minute, timezone) is posted
 * to Django, which composes the UTC instant with zoneinfo and re-checks the
 * scheduling rules — see apps/bookings/timezones.py and forms.py. Nothing here
 * is trusted.
 */

/** Forgiving typed time, Google Calendar style.
 *  Accepts "14", "14:35", "1435", "935", "2pm", "2:37 pm", "14.35", "2:3" (→ 2:30). */
function parseTimeInput(raw) {
  let s = String(raw).trim().toLowerCase().replace(/\s+/g, "").replace(/\./g, ":");
  if (!s) return null;

  let meridiem = null;
  const m = s.match(/(am|pm|a|p)$/);
  if (m) {
    meridiem = m[1].startsWith("a") ? "am" : "pm";
    s = s.slice(0, -m[1].length);
  }
  if (!/^\d{1,4}(:\d{0,2})?$/.test(s)) return null;

  let h, min;
  if (s.includes(":")) {
    const [hs = "", ms = ""] = s.split(":");
    h = Number(hs);
    // A single minute digit means tens: "2:3" → 2:30, like Google.
    min = ms === "" ? 0 : ms.length === 1 ? Number(ms) * 10 : Number(ms);
  } else if (s.length <= 2) {
    h = Number(s);
    min = 0;
  } else {
    h = Number(s.slice(0, -2));
    min = Number(s.slice(-2));
  }

  if (meridiem === "pm" && h < 12) h += 12;
  if (meridiem === "am" && h === 12) h = 0;
  if (!Number.isFinite(h) || !Number.isFinite(min) || h > 23 || min > 59) return null;

  return { h, m: min };
}

const pad = (n) => String(n).padStart(2, "0");
const fmtTime = (t) => `${pad(t.h)}:${pad(t.m)}`;
const isoDate = (d) =>
  `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

document.addEventListener("alpine:init", () => {
  Alpine.data("bookingPage", (config) => ({
    exams: config.exams,
    timezones: config.timezones,
    timezone: config.defaultTimezone,
    examSlug: config.preselected || "",

    dateValue: "",
    time: { h: 9, m: 0 },
    timeText: "09:00",
    timeOpen: false,
    month: null,

    init() {
      // Prefer the browser's own zone when we offer it.
      const browser = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (this.timezones.some((t) => t.value === browser)) this.timezone = browser;
      this.month = this.startOfMonth(this.earliest);
    },

    // ---- exam ----
    get exam() {
      return this.exams.find((e) => e.slug === this.examSlug) || null;
    },
    reset() {
      this.dateValue = "";
      this.month = this.startOfMonth(this.earliest);
    },

    // ---- bounds ----
    get earliest() {
      const d = new Date();
      d.setHours(0, 0, 0, 0);
      d.setDate(d.getDate() + config.minDaysAhead);
      return d;
    },
    get latest() {
      const d = new Date();
      d.setHours(0, 0, 0, 0);
      d.setMonth(d.getMonth() + config.maxMonthsAhead);
      return d;
    },
    startOfMonth(d) {
      return new Date(d.getFullYear(), d.getMonth(), 1);
    },

    // ---- calendar ----
    get monthLabel() {
      return this.month.toLocaleDateString(undefined, {
        month: "long",
        year: "numeric",
      });
    },
    get canGoBack() {
      return this.month > this.startOfMonth(this.earliest);
    },
    get canGoForward() {
      return this.month < this.startOfMonth(this.latest);
    },
    prevMonth() {
      if (this.canGoBack) this.month = new Date(this.month.getFullYear(), this.month.getMonth() - 1, 1);
    },
    nextMonth() {
      if (this.canGoForward) this.month = new Date(this.month.getFullYear(), this.month.getMonth() + 1, 1);
    },
    get monthGrid() {
      const first = this.startOfMonth(this.month);
      const start = new Date(first);
      start.setDate(1 - first.getDay());

      const cells = [];
      for (let i = 0; i < 42; i += 1) {
        const d = new Date(start);
        d.setDate(start.getDate() + i);
        const iso = isoDate(d);
        cells.push({
          key: iso,
          iso,
          day: d.getDate(),
          inMonth: d.getMonth() === first.getMonth(),
          selectable:
            d.getMonth() === first.getMonth() &&
            d >= this.earliest &&
            d <= this.latest,
        });
      }
      return cells;
    },
    selectDay(iso) {
      this.dateValue = iso;
      this.emit();
    },

    // ---- time ----
    get timeSuggestions() {
      const all = [];
      for (let i = 0; i < 24 * 4; i += 1) {
        all.push(fmtTime({ h: Math.floor(i / 4), m: (i % 4) * 15 }));
      }
      const typed = parseTimeInput(this.timeText);
      if (!typed) return all;
      const exact = fmtTime(typed);
      return [exact, ...all.filter((s) => s !== exact)];
    },
    commitTime() {
      const parsed = parseTimeInput(this.timeText);
      if (parsed) {
        this.time = parsed;
        this.timeText = fmtTime(parsed);
        this.emit();
      } else {
        this.timeText = fmtTime(this.time);
      }
    },

    // ---- timezone ----
    get zoneOption() {
      return this.timezones.find((t) => t.value === this.timezone) || null;
    },
    get gmtLabel() {
      return this.zoneOption ? this.zoneOption.label : "";
    },
    get placeLabel() {
      return this.zoneOption ? this.zoneOption.place : "";
    },

    // ---- display ----
    get longDate() {
      if (!this.dateValue) return "";
      const [y, m, d] = this.dateValue.split("-").map(Number);
      return new Date(y, m - 1, d).toLocaleDateString(undefined, {
        weekday: "long",
        month: "long",
        day: "numeric",
      });
    },
    get summary() {
      if (!this.dateValue) return "";
      return `${this.longDate} · ${fmtTime(this.time)}`;
    },

    /** Nothing to compute — Django owns the UTC conversion. Kept as the single
     *  place to hook validation or a live preview later. */
    emit() {},
  }));
});
