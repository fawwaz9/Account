/** The current day and minute in one time zone. */
export interface ZonedNow {
  /** Local calendar day, YYYY-MM-DD. */
  readonly date: string;
  /** Minutes since that day's midnight, 0-1439. */
  readonly minutes: number;
}

/**
 * Now on the Settings time zone's clock, matching the backend's "today".
 * A missing or invalid zone falls back to the browser clock instead of throwing.
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
