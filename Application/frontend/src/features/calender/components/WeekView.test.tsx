// @vitest-environment jsdom
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { EventOccurrence } from "../types";
import { CalendarDay } from "../hooks/useCalender";
import { HOUR_HEIGHT } from "../weekLayout";

/**
 * The current-time line, and the colours a student chose.
 *
 * The process clock is pinned to America/Regina by vitest.config.ts, so every
 * zone case here crosses midnight against it: a test that only used Regina would
 * pass against the browser clock too, and prove nothing about the setting.
 */
const auth = { user: { preferences: { timezone: "America/Regina", event_colors: {} as Record<string, string> } } };
vi.mock("../../../app/auth/AuthContext", () => ({ useAuth: () => auth }));

const { default: WeekView } = await import("./WeekView");

// Monday 28 September to Sunday 4 October 2026.
const WEEK = ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"];
const NEXT_WEEK = ["2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09", "2026-10-10", "2026-10-11"];

function occurrence(over: Partial<EventOccurrence>): EventOccurrence {
  return {
    event_id: "e1", on_date: "2026-10-01", title: "CPSC 320", kind: "lecture",
    start_time: "10:00:00", end_time: "11:00:00", location: null, notes: null,
    course_id: null, course_code: null, job_id: null, repeats: false, grade_id: null,
    ...over,
  };
}

function days(dates: string[], occurrences: EventOccurrence[] = []): CalendarDay[] {
  return dates.map((date) => ({ date, tasks: [], occurrences: occurrences.filter((o) => o.on_date === date) }));
}

function show(dates = WEEK, occurrences: EventOccurrence[] = []) {
  return render(
    <WeekView days={days(dates, occurrences)} loading={false}
      onSelectOccurrence={() => {}} onSelectTask={() => {}} onAddOnDay={() => {}} />,
  );
}

/** Which day's column holds the line, or null. */
function lineDay(container: HTMLElement, dates = WEEK): string | null {
  const columns = [...container.querySelectorAll(".weekColumn")];
  const index = columns.findIndex((column) => column.querySelector(".weekNow"));
  return index === -1 ? null : dates[index];
}

function todayHeading(container: HTMLElement, dates = WEEK): string | null {
  const heads = [...container.querySelectorAll(".weekHead")];
  const index = heads.findIndex((head) => head.classList.contains("weekHeadToday"));
  return index === -1 ? null : dates[index];
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date", "setTimeout", "setInterval", "clearTimeout", "clearInterval"] });
  // 19:30 on Saturday the 3rd in Regina; already 01:30 on Sunday the 4th in UTC.
  vi.setSystemTime(new Date("2026-10-04T01:30:00Z"));
  auth.user.preferences.timezone = "America/Regina";
  auth.user.preferences.event_colors = {};
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("the current-time line", () => {
  it("is drawn in today's column, at the current minute", () => {
    const { container } = show();

    expect(lineDay(container)).toBe("2026-10-03");
    const line = container.querySelector<HTMLElement>(".weekNow")!;
    expect(line.style.top).toBe(`${19.5 * HOUR_HEIGHT}px`);
  });

  it("is drawn exactly once", () => {
    const { container } = show();
    expect(container.querySelectorAll(".weekNow")).toHaveLength(1);
  });

  it("is not drawn on a week that is not this one", () => {
    const { container } = show(NEXT_WEEK);
    expect(container.querySelector(".weekNow")).toBeNull();
  });

  it("follows the Settings zone, not the browser's, across midnight", () => {
    auth.user.preferences.timezone = "UTC";
    const { container } = show();

    expect(lineDay(container)).toBe("2026-10-04");
    expect(container.querySelector<HTMLElement>(".weekNow")!.style.top).toBe(`${1.5 * HOUR_HEIGHT}px`);
  });

  it("highlights the same column as today that the line is in", () => {
    for (const zone of ["America/Regina", "UTC"]) {
      auth.user.preferences.timezone = zone;
      const { container } = show();
      expect(todayHeading(container), zone).toBe(lineDay(container));
      cleanup();
    }
  });

  it("moves when the minute changes", () => {
    const { container } = show();
    const before = container.querySelector<HTMLElement>(".weekNow")!.style.top;

    act(() => { vi.advanceTimersByTime(60_000); });

    const after = container.querySelector<HTMLElement>(".weekNow")!.style.top;
    expect(after).not.toBe(before);
    expect(after).toBe(`${(19.5 + 1 / 60) * HOUR_HEIGHT}px`);
  });

  it("is hidden from assistive technology", () => {
    const { container } = show();
    expect(container.querySelector(".weekNow")!.getAttribute("aria-hidden")).toBe("true");
  });

  it("never takes a click meant for the block under it", () => {
    // jsdom applies no stylesheet, so this reads the rule itself.
    const css = readFileSync(join(__dirname, "../../../styles/calendar.css"), "utf8");
    const rule = css.match(/\.weekNow\s*\{([^}]*)\}/);
    expect(rule?.[1]).toMatch(/pointer-events:\s*none/);
  });
});

describe("chosen event colours", () => {
  it("applies a chosen colour to that kind's block", () => {
    auth.user.preferences.event_colors = { lecture: "#123456" };
    const { container } = show(WEEK, [occurrence({})]);

    const block = container.querySelector<HTMLElement>(".weekBlock")!;
    expect(block.style.getPropertyValue("--kind-color")).toBe("#123456");
  });

  it("leaves an unchanged kind to the stylesheet", () => {
    auth.user.preferences.event_colors = { lab: "#123456" };
    const { container } = show(WEEK, [occurrence({})]);

    const block = container.querySelector<HTMLElement>(".weekBlock")!;
    expect(block.style.getPropertyValue("--kind-color")).toBe("");
  });

  it("applies it to an all-day chip as well", () => {
    auth.user.preferences.event_colors = { deadline: "#654321" };
    const { container } = show(WEEK, [occurrence({ kind: "deadline", start_time: null, end_time: null })]);

    const chip = container.querySelector<HTMLElement>(".weekAllDay .calChip")!;
    expect(chip.style.getPropertyValue("--kind-color")).toBe("#654321");
  });
});
