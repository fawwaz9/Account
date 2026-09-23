import { describe, expect, it } from "vitest";
import {
  addDays,
  addMonths,
  firstOfMonth,
  fromIso,
  isoDate,
  lastOfMonth,
  startOfWeek,
  today,
  weekdayCode,
  weekdayIndex,
} from "./dateUtils";

/**
 * The timezone these tests are written against.
 *
 * Asserted rather than assumed: every assertion below depends on the suite
 * running at UTC-6, and if `vitest.config.ts` ever stops applying it they
 * should fail here saying why, rather than fail one by one somewhere that
 * reads as a date bug.
 */
describe("the clock these tests run on", () => {
  it("is UTC-6, in both halves of the year", () => {
    expect(new Date(2026, 0, 1).getTimezoneOffset()).toBe(360);
    expect(new Date(2026, 6, 1).getTimezoneOffset()).toBe(360);
  });
});

describe("fromIso", () => {
  /**
   * The bug this function exists to prevent, stated as a test.
   *
   * `new Date("2026-09-08")` parses as UTC midnight, which is 18:00 on the 7th
   * here -- so the naive version renders the day before for every reader west
   * of Greenwich and is perfectly correct for everyone east of it.
   */
  it("reads a plain date as a local date, not as UTC midnight", () => {
    const parsed = fromIso("2026-09-08");

    expect(parsed.getFullYear()).toBe(2026);
    expect(parsed.getMonth()).toBe(8);
    expect(parsed.getDate()).toBe(8);

    // The thing it must not do, pinned so the reason survives.
    expect(new Date("2026-09-08").getDate()).toBe(7);
  });

  it("round-trips through isoDate", () => {
    expect(isoDate(fromIso("2026-09-08"))).toBe("2026-09-08");
    expect(isoDate(fromIso("2026-01-01"))).toBe("2026-01-01");
  });
});

describe("addDays", () => {
  it("crosses a month end", () => {
    expect(addDays("2026-09-30", 1)).toBe("2026-10-01");
  });

  it("crosses a year end, forwards and back", () => {
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2027-01-01", -1)).toBe("2026-12-31");
  });
});

describe("addMonths", () => {
  /**
   * Stepping a month from the 31st is the case that goes wrong silently:
   * JavaScript rolls 31 February forward into March, so "next month" from
   * 31 January would be March and a monthly figure would skip February
   * altogether. Anchoring to the 1st first is what avoids it.
   */
  it("does not skip a month when stepping from the 31st", () => {
    expect(addMonths("2026-01-31", 1)).toBe("2026-02-01");
  });

  it("steps whole months either way", () => {
    expect(addMonths("2026-09-01", 1)).toBe("2026-10-01");
    expect(addMonths("2026-01-15", -1)).toBe("2025-12-01");
  });
});

describe("month edges", () => {
  it("firstOfMonth keeps the month it was given", () => {
    expect(firstOfMonth("2026-09-08")).toBe("2026-09-01");
  });

  it("lastOfMonth handles a short month", () => {
    expect(lastOfMonth("2026-02-10")).toBe("2026-02-28");
    expect(lastOfMonth("2026-09-08")).toBe("2026-09-30");
  });
});

describe("weeks start on Monday, where a timetable starts", () => {
  it("indexes Monday as 0 and Sunday as 6", () => {
    expect(weekdayIndex(fromIso("2026-09-07"))).toBe(0); // Monday
    expect(weekdayIndex(fromIso("2026-09-13"))).toBe(6); // Sunday
  });

  it("walks back to Monday", () => {
    // 2026-09-08 is a Tuesday.
    expect(startOfWeek("2026-09-08")).toBe("2026-09-07");
    // Already Monday: unchanged, rather than a week early.
    expect(startOfWeek("2026-09-07")).toBe("2026-09-07");
    // Sunday belongs to the week that began six days earlier.
    expect(startOfWeek("2026-09-13")).toBe("2026-09-07");
  });

  it("emits the codes the API uses for byday", () => {
    expect(weekdayCode("2026-09-07")).toBe("MO");
    expect(weekdayCode("2026-09-13")).toBe("SU");
  });
});

describe("today", () => {
  it("is the local date, in the same format every other date uses", () => {
    expect(today()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(today()).toBe(isoDate(new Date()));
  });
});
