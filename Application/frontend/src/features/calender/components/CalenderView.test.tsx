// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setClockZone } from "../../../shared/utils/dateUtils";

vi.mock("../../../app/auth/AuthContext", () => ({ useAuth: () => ({ user: null }) }));
const { default: CalenderView } = await import("./CalenderView");

/** The month view's "today" -- the item this change was opened for. */
const DATES = ["2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05"];

function todayCell(container: HTMLElement): string | null {
  const cells = [...container.querySelectorAll(".calCell")];
  const index = cells.findIndex((cell) => cell.classList.contains("calCellToday"));
  return index === -1 ? null : DATES[index];
}

function show() {
  return render(
    <CalenderView month="2026-10-01" loading={false}
      days={DATES.map((date) => ({ date, occurrences: [], tasks: [] }))}
      onSelectOccurrence={() => {}} onSelectTask={() => {}} onAddOnDay={() => {}} />,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-04T01:30:00Z")); // 3rd in Regina, 4th in UTC
});

afterEach(() => {
  cleanup();
  setClockZone(null);
  vi.useRealTimers();
});

describe("the month view's today", () => {
  it("marks the Settings zone's day, not the browser's", () => {
    setClockZone("UTC");
    expect(todayCell(show().container)).toBe("2026-10-04");
  });

  it("marks the browser's day before a zone is known", () => {
    expect(todayCell(show().container)).toBe("2026-10-03");
  });
});
