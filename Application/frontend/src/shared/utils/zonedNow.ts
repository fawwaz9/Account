export interface ZonedNow {
  /** The calendar day where the student is, as YYYY-MM-DD. */
  readonly date: string;
  /** Minutes since that day's midnight, 0-1439. */
  readonly minutes: number;
}

/**
 * Now, on the clock of the time zone in Settings rather than the browser's.
 *
 * The backend reads "today" from that zone (`app/shared/dates.py`), and a week
 * view drawing the current time from a different clock would put the line in a
 * different column from the one every server figure treats as today. The two
 * only differ when the device and the setting disagree -- travelling, usually --
 * which is exactly when a quietly wrong line is most misleading.
 *
 * An unusable zone falls back to the browser clock rather than throwing, the
 * same choice the backend makes: a missing line is worse than an approximate one.
 */
export function nowIn(zone: string | null | undefined, at: Date = new Date()): ZonedNow {
  try {
    if (!zone) throw new RangeError("no zone");
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: zone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(at);
    const part = (type: Intl.DateTimeFormatPartTypes) =>
      parts.find((item) => item.type === type)?.value ?? "";

    return {
      date: `${part("year")}-${part("month")}-${part("day")}`,
      minutes: Number(part("hour")) * 60 + Number(part("minute")),
    };
  } catch {
    // Spelled out rather than imported: dateUtils' today() is built on this
    // function, so importing back from it would make the two a cycle.
    const pad = (value: number) => String(value).padStart(2, "0");
    return {
      date: `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}`,
      minutes: at.getHours() * 60 + at.getMinutes(),
    };
  }
}
