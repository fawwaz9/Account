/** One place that decides what "today" is, the way money.ts decides how money reads. */

function pad(value: number) {
  return String(value).padStart(2, "0");
}

/**
 * Today as YYYY-MM-DD in the viewer's own timezone.
 *
 * Deliberately not `toISOString().slice(0, 10)`, which is UTC: west of
 * Greenwich that returns tomorrow's date all evening, so an expense recorded
 * after dinner was being filed on the following day.
 */
export function localToday(): string {
  return isoDate(new Date());
}

/** A date `count` days before today, same format and same timezone rule. */
export function daysAgo(count: number): string {
  const day = new Date();
  day.setDate(day.getDate() - count);
  return isoDate(day);
}

/** A date `count` days after today, same format and same timezone rule. */
export function daysAhead(count: number): string {
  const day = new Date();
  day.setDate(day.getDate() + count);
  return isoDate(day);
}

/** First of the current month, which is how a month is keyed throughout. */
export function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-01`;
}

/** First of the month a YYYY-MM-DD date falls in. */
export function firstOfMonth(day: string): string {
  return `${day.slice(0, 7)}-01`;
}

function isoDate(day: Date): string {
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
}
