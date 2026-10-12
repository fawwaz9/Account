import { describe, expect, it } from "vitest";
import {
  CalendarView,
  defaultView,
  fitView,
  stepCursor,
  stepNoun,
  viewLabel,
  viewsFor,
  windowDays,
} from "./views";
import { weekLabel } from "../../shared/utils/dateUtils";

/**
 * The phone views (next.md, Calendar): one day and three days in place of the
 * week, whose seven columns are too narrow to read on a phone.
 *
 * Thursday 29 October 2026 is the anchor throughout, so a three-day window runs
 * into the next month and a week straddles none.
 */
const THU = "2026-10-29";

describe("which views a width offers", () => {
  it("gives a phone a day, three days and the month, and no week", () => {
    expect(viewsFor(true)).toEqual(["day", "3day", "month"]);
  });

  it("leaves the desktop with the week and the month", () => {
    expect(viewsFor(false)).toEqual(["week", "month"]);
  });

  it("opens a phone on three days and a desktop on the week", () => {
    expect(defaultView(true)).toBe("3day");
    expect(defaultView(false)).toBe("week");
  });

  it("never opens on a view the width does not offer", () => {
    for (const phone of [true, false]) {
      expect(viewsFor(phone)).toContain(defaultView(phone));
    }
  });
});

describe("crossing the breakpoint", () => {
  it("turns a week into three days on a phone", () => {
    expect(fitView("week", true)).toBe("3day");
  });

  it("turns a day or three days into a week on a desktop", () => {
    expect(fitView("day", false)).toBe("week");
    expect(fitView("3day", false)).toBe("week");
  });

  it("keeps a view the width offers", () => {
    expect(fitView("month", true)).toBe("month");
    expect(fitView("month", false)).toBe("month");
    expect(fitView("day", true)).toBe("day");
    expect(fitView("week", false)).toBe("week");
  });

  it("always lands on a view the width offers", () => {
    const all: CalendarView[] = ["day", "3day", "week", "month"];
    for (const phone of [true, false]) {
      for (const view of all) expect(viewsFor(phone)).toContain(fitView(view, phone));
    }
  });
});

describe("the dates a view shows", () => {
  it("shows the cursor's day alone", () => {
    expect(windowDays("day", THU)).toEqual([THU]);
  });

  it("starts three days at the cursor, not at a week, and runs into the next month", () => {
    expect(windowDays("3day", THU)).toEqual(["2026-10-29", "2026-10-30", "2026-10-31"]);
    expect(windowDays("3day", "2026-10-30")).toEqual(["2026-10-30", "2026-10-31", "2026-11-01"]);
  });

  it("keeps the week Monday to Sunday", () => {
    expect(windowDays("week", THU)).toEqual([
      "2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30", "2026-10-31", "2026-11-01",
    ]);
  });

  it("keeps the month's six-week grid", () => {
    const month = windowDays("month", THU);
    expect(month).toHaveLength(42);
    expect(month[0]).toBe("2026-09-28");
  });
});

describe("one press of an arrow", () => {
  it.each([
    ["day", "2026-10-30", "2026-10-28"],
    ["3day", "2026-11-01", "2026-10-26"],
    ["week", "2026-11-05", "2026-10-22"],
    ["month", "2026-11-01", "2026-09-01"],
  ] as const)("moves %s forward to %s and back to %s", (view, forward, back) => {
    expect(stepCursor(view, THU, 1)).toBe(forward);
    expect(stepCursor(view, THU, -1)).toBe(back);
  });

  it("moves three days a whole page, so no day is shown twice", () => {
    const first = windowDays("3day", THU);
    const next = windowDays("3day", stepCursor("3day", THU, 1));
    expect(next[0]).toBe("2026-11-01");
    expect(first.filter((date) => next.includes(date))).toEqual([]);
  });

  it("names what it moves by", () => {
    expect(stepNoun("day")).toBe("day");
    expect(stepNoun("3day")).toBe("3 days");
    expect(stepNoun("week")).toBe("week");
    expect(stepNoun("month")).toBe("month");
  });
});

describe("the heading", () => {
  it("names a day with its weekday and year", () => {
    expect(viewLabel("day", THU)).toBe("Thu 29 Oct 2026");
  });

  it("collapses three days inside one month", () => {
    expect(viewLabel("3day", "2026-10-12")).toBe("12 – 14 Oct 2026");
  });

  it("names both months when three days cross one", () => {
    expect(viewLabel("3day", "2026-10-30")).toBe("30 Oct – 1 Nov 2026");
  });

  it("names both years when three days cross one", () => {
    expect(viewLabel("3day", "2026-12-31")).toBe("31 Dec 2026 – 2 Jan 2027");
  });

  it("leaves the week's heading as it was", () => {
    expect(viewLabel("week", THU)).toBe(weekLabel(THU));
    expect(weekLabel(THU)).toBe("26 Oct – 1 Nov 2026");
    expect(weekLabel("2026-09-10")).toBe("7 – 13 Sep 2026");
  });

  it("leaves the month's heading as it was", () => {
    expect(viewLabel("month", THU)).toBe("October 2026");
  });
});
