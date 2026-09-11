/**
 * Calendar date arithmetic, in the viewer's own timezone.
 *
 * Every date in this app is a plain YYYY-MM-DD: a lecture at 10:00 is at 10:00
 * wherever you read it from. So the rule here matches `features/budget/dates.ts`
 * -- never `toISOString()`, which is UTC and, west of Greenwich, reports
 * tomorrow's date all evening.
 */

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

export function today(): string {
  return isoDate(new Date());
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
