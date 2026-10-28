/** YYYY-MM-DD date helpers in local time, never `toISOString`; today reads the Settings zone. */

import { nowIn } from "./zonedNow";

/** Short English weekday names, Monday first. */
const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

/** The API's byday codes, Monday first; each index matches `weekdayIndex`. */
export const WEEKDAY_CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"] as const;

/** One of the API's two-letter byday codes. */
export type WeekdayCode = (typeof WEEKDAY_CODES)[number];

/** Zero-pad a number to two digits. */
function pad(value: number) {
  return String(value).padStart(2, "0");
}

/** Format a Date as YYYY-MM-DD in local time. */
export function isoDate(day: Date): string {
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
}

/**
 * Parse YYYY-MM-DD as local midnight.
 * Never `new Date(value)`, which reads UTC and lands on the day before west of Greenwich.
 */
export function fromIso(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

/** Zone `today` reads, set from Settings by AuthProvider; null means the browser's zone. */
let clockZone: string | null = null;

/** Set the zone `today` reads; AuthProvider calls it whenever the signed-in user changes. */
export function setClockZone(zone: string | null | undefined): void {
  clockZone = zone || null;
}

/** Today as YYYY-MM-DD in the Settings time zone, or the browser's before sign-in. */
export function today(): string {
  return nowIn(clockZone).date;
}

/** Shift a YYYY-MM-DD date by `count` days; negative goes back. */
export function addDays(value: string, count: number): string {
  const day = fromIso(value);
  day.setDate(day.getDate() + count);
  return isoDate(day);
}

/** The 1st of the month `count` months from `value`'s month (the day is not kept). */
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

/** Weekday of a Date as 0 (Monday) to 6 (Sunday). */
export function weekdayIndex(day: Date): number {
  return (day.getDay() + 6) % 7;
}

/** The API byday code of a YYYY-MM-DD date. */
export function weekdayCode(value: string): WeekdayCode {
  return WEEKDAY_CODES[weekdayIndex(fromIso(value))];
}

/** First day of `value`'s month. */
export function firstOfMonth(value: string): string {
  return `${value.slice(0, 7)}-01`;
}

/** Last day of `value`'s month. */
export function lastOfMonth(value: string): string {
  return addDays(addMonths(firstOfMonth(value), 1), -1);
}

/** The 42 days of six Monday-first weeks covering `month`, so the grid never changes height. */
export function monthGrid(month: string): string[] {
  const start = startOfWeek(firstOfMonth(month));
  return Array.from({ length: 42 }, (_, index) => addDays(start, index));
}

/** The seven days, Monday first, of the week `value` falls in. */
export function weekGrid(value: string): string[] {
  const start = startOfWeek(value);
  return Array.from({ length: 7 }, (_, index) => addDays(start, index));
}

/** "HH:MM[:SS]" as minutes since midnight; null when there is no time (an all-day item). */
export function minutesOfDay(value: string | null): number | null {
  if (!value) return null;

  const [hours, minutes] = value.split(":").map(Number);
  return hours * 60 + minutes;
}

/** Hour 0-23 as a time-axis label: "12am", "9am", "1pm". */
export function hourLabel(hour: number): string {
  const suffix = hour < 12 ? "am" : "pm";
  const display = hour % 12 === 0 ? 12 : hour % 12;
  return `${display}${suffix}`;
}

/** True when both dates share a year and month. */
export function isSameMonth(value: string, month: string): boolean {
  return value.slice(0, 7) === month.slice(0, 7);
}

/** "Tue 8 Sep": English weekday, day of month, short month in the browser's locale. */
export function shortDate(value: string): string {
  const day = fromIso(value);
  return `${WEEKDAY_LABELS[weekdayIndex(day)]} ${day.getDate()} ${monthName(value, true)}`;
}

/** Month name of a date in the browser's locale, long or short. */
export function monthName(value: string, short = false): string {
  return fromIso(value).toLocaleString(undefined, { month: short ? "short" : "long" });
}

/** Month and year for a heading, e.g. "September 2026". */
export function monthLabel(value: string): string {
  return `${monthName(value)} ${fromIso(value).getFullYear()}`;
}

/** Range label for the Monday-to-Sunday week holding `value`, e.g. "8 – 14 Sep 2026". */
export function weekLabel(value: string): string {
  const days = weekGrid(value);
  return rangeLabel(days[0], days[6]);
}

/** "8 – 14 Sep 2026": a date range that repeats the month or year only when they differ. */
export function rangeLabel(first: string, last: string): string {
  const start = fromIso(first);
  const end = fromIso(last);

  const endPart = `${end.getDate()} ${monthName(last, true)} ${end.getFullYear()}`;
  if (start.getFullYear() !== end.getFullYear()) {
    return `${start.getDate()} ${monthName(first, true)} ${start.getFullYear()} – ${endPart}`;
  }
  if (start.getMonth() !== end.getMonth()) {
    return `${start.getDate()} ${monthName(first, true)} – ${endPart}`;
  }
  return `${start.getDate()} – ${endPart}`;
}

/** "09:30" or "09:30:00" as "9:30am", "14:00" as "2pm"; "" for null. */
export function clockTime(value: string | null): string {
  if (!value) return "";

  const [hours, minutes] = value.split(":").map(Number);
  const suffix = hours < 12 ? "am" : "pm";
  const hour = hours % 12 === 0 ? 12 : hours % 12;
  return minutes === 0 ? `${hour}${suffix}` : `${hour}:${pad(minutes)}${suffix}`;
}

/** Minutes as "45m", "2h" or "1h 30m"; "" for null, zero or negative. */
export function duration(minutes: number | null | undefined): string {
  if (!minutes || minutes <= 0) return "";

  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest}m`;
  return rest === 0 ? `${hours}h` : `${hours}h ${rest}m`;
}

/**
 * A date relative to today: "Today", "Tomorrow", "in 3 days", "Yesterday", "4 days ago".
 * Fourteen or more days ahead reads as `shortDate`; "" for null.
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

/** Whole calendar days from `from` to `to`; negative when `to` is earlier. */
export function daysBetween(from: string, to: string): number {
  const millis = fromIso(to).getTime() - fromIso(from).getTime();
  return Math.round(millis / 86_400_000);
}
