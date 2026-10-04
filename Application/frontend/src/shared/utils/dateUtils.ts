/**
 * Calendar date arithmetic. "Today" is read in the student's Settings time zone
 * (see `setClockZone`); everything else here is plain date arithmetic.
 *
 * Every date in this app is a plain YYYY-MM-DD: a lecture at 10:00 is at 10:00
 * wherever you read it from. So the rule here matches `features/budget/dates.ts`
 * -- never `toISOString()`, which is UTC and, west of Greenwich, reports
 * tomorrow's date all evening.
 */

import { nowIn } from "./zonedNow";

const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

/** Matches the API's byday codes, and the index matches `weekdayIndex`. */
export const WEEKDAY_CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"] as const;

export type WeekdayCode = (typeof WEEKDAY_CODES)[number];

function pad(value: number) {
  return String(value).padStart(2, "0");
}

/** A Date as YYYY-MM-DD, read in local time. */
export function isoDate(day: Date): string {
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
}

/**
 * A YYYY-MM-DD string as a local Date at midnight.
 *
 * `new Date("2026-09-08")` parses as UTC midnight, which renders as the 7th
 * anywhere west of Greenwich -- an off-by-one that only shows up for some
 * readers, which is the worst kind.
 */
export function fromIso(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

/**
 * The time zone "today" is read in: the student's Settings zone once the
 * signed-in user is known, and the browser's until then.
 *
 * Module state, set by AuthProvider, rather than a zone passed to every caller:
 * over forty places ask for today, and each one threading a zone through is
 * forty chances to forget it. The backend reads today from the same setting
 * (`app/shared/dates.py`), so the page and every figure the server sends now
 * agree about which day it is -- which they did not when the device's zone and
 * the setting differed, travelling for instance.
 */
let clockZone: string | null = null;

/** Called by AuthProvider whenever the signed-in user changes. */
export function setClockZone(zone: string | null | undefined): void {
  clockZone = zone || null;
}

export function today(): string {
  return nowIn(clockZone).date;
}

export function addDays(value: string, count: number): string {
  const day = fromIso(value);
  day.setDate(day.getDate() + count);
  return isoDate(day);
}

export function addMonths(value: string, count: number): string {
  const day = fromIso(value);
  // Anchor to the 1st first: stepping from the 31st lands in the month after
  // the one intended, because JavaScript rolls the overflow forward.
  day.setDate(1);
  day.setMonth(day.getMonth() + count);
  return isoDate(day);
}

/** Monday of the week `value` falls in. */
export function startOfWeek(value: string): string {
  const day = fromIso(value);
  return addDays(value, -weekdayIndex(day));
}

/** 0 for Monday through 6 for Sunday, so a week starts where a timetable does. */
export function weekdayIndex(day: Date): number {
  return (day.getDay() + 6) % 7;
}

export function weekdayCode(value: string): WeekdayCode {
  return WEEKDAY_CODES[weekdayIndex(fromIso(value))];
}

export function firstOfMonth(value: string): string {
  return `${value.slice(0, 7)}-01`;
}

export function lastOfMonth(value: string): string {
  return addDays(addMonths(firstOfMonth(value), 1), -1);
}

/**
 * The six weeks a month grid draws: whole weeks, Monday-first, covering the
 * month and the days either side of it that share those weeks.
 *
 * Always six rows rather than however many the month needs, so the grid does
 * not change height as you page through the term.
 */
export function monthGrid(month: string): string[] {
  const start = startOfWeek(firstOfMonth(month));
  return Array.from({ length: 42 }, (_, index) => addDays(start, index));
}

/** The seven days of the week `value` falls in, Monday first. */
export function weekGrid(value: string): string[] {
  const start = startOfWeek(value);
  return Array.from({ length: 7 }, (_, index) => addDays(start, index));
}

/**
 * "HH:MM[:SS]" as minutes since midnight, which is what a timed grid positions
 * against. Null for an all-day item, which has no position on that axis.
 */
export function minutesOfDay(value: string | null): number | null {
  if (!value) return null;

  const [hours, minutes] = value.split(":").map(Number);
  return hours * 60 + minutes;
}

/** "9am", "1pm" — an hour label for a time axis, where minutes are always zero. */
export function hourLabel(hour: number): string {
  const suffix = hour < 12 ? "am" : "pm";
  const display = hour % 12 === 0 ? 12 : hour % 12;
  return `${display}${suffix}`;
}

export function isSameMonth(value: string, month: string): boolean {
  return value.slice(0, 7) === month.slice(0, 7);
}

/** "Tue 8 Sep" -- short enough for a chip, unambiguous about the weekday. */
export function shortDate(value: string): string {
  const day = fromIso(value);
  return `${WEEKDAY_LABELS[weekdayIndex(day)]} ${day.getDate()} ${monthName(value, true)}`;
}

export function monthName(value: string, short = false): string {
  return fromIso(value).toLocaleString(undefined, { month: short ? "short" : "long" });
}

/** "September 2026", for a calendar heading. */
export function monthLabel(value: string): string {
  return `${monthName(value)} ${fromIso(value).getFullYear()}`;
}

/**
 * "8 – 14 Sep 2026", collapsing whatever the two ends share.
 *
 * A week that straddles a month or a year has to say so; one that does not
 * should not repeat itself.
 */
export function weekLabel(value: string): string {
  const days = weekGrid(value);
  const start = fromIso(days[0]);
  const end = fromIso(days[6]);

  const endPart = `${end.getDate()} ${monthName(days[6], true)} ${end.getFullYear()}`;
  if (start.getFullYear() !== end.getFullYear()) {
    return `${start.getDate()} ${monthName(days[0], true)} ${start.getFullYear()} – ${endPart}`;
  }
  if (start.getMonth() !== end.getMonth()) {
    return `${start.getDate()} ${monthName(days[0], true)} – ${endPart}`;
  }
  return `${start.getDate()} – ${endPart}`;
}

/** "09:30" -> "9:30 am". Times arrive from the API as HH:MM or HH:MM:SS. */
export function clockTime(value: string | null): string {
  if (!value) return "";

  const [hours, minutes] = value.split(":").map(Number);
  const suffix = hours < 12 ? "am" : "pm";
  const hour = hours % 12 === 0 ? 12 : hours % 12;
  return minutes === 0 ? `${hour}${suffix}` : `${hour}:${pad(minutes)}${suffix}`;
}

/** "1h 30m" from a count of minutes; "" for nothing. */
export function duration(minutes: number | null | undefined): string {
  if (!minutes || minutes <= 0) return "";

  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest}m`;
  return rest === 0 ? `${hours}h` : `${hours}h ${rest}m`;
}

/**
 * How a deadline reads relative to today: "Overdue", "Today", "in 3 days".
 *
 * Whole days apart rather than hours, so something due at 9am tomorrow reads as
 * tomorrow all evening rather than becoming "in 14 hours".
 */
export function dueLabel(value: string | null): string {
  if (!value) return "";

  const days = daysBetween(today(), value);
  if (days < 0) return days === -1 ? "Yesterday" : `${Math.abs(days)} days ago`;
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days <= 13) return `in ${days} days`;
  return shortDate(value);
}

/** Whole days from `from` to `to`; negative when `to` is earlier. */
export function daysBetween(from: string, to: string): number {
  const millis = fromIso(to).getTime() - fromIso(from).getTime();
  return Math.round(millis / 86_400_000);
}
