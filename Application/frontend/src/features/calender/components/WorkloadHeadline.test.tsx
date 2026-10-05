// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import WorkloadHeadline from "./WorkloadHeadline";

afterEach(cleanup);

const base = { estimatedMinutes: 14 * 60, taskCount: 8, unestimatedTasks: 0, freeMinutes: 20 * 60 };

function text(forecast: typeof base) {
  return render(<WorkloadHeadline forecast={forecast} />).container.textContent ?? "";
}

describe("WorkloadHeadline", () => {
  it("sets estimated work against free time", () => {
    const t = text(base);
    expect(t).toContain("Next 7 days: 14h of estimated work, 20h free in your study hours.");
    expect(t).not.toContain("More work than free time");
    expect(t).not.toContain("no estimate");
  });

  it("says so when the work does not fit", () => {
    expect(text({ ...base, freeMinutes: 9 * 60 + 30 })).toContain("9h 30m free");
    expect(text({ ...base, freeMinutes: 9 * 60 })).toContain("More work than free time.");
  });

  it("calls the figure a floor when some tasks have no estimate", () => {
    expect(text({ ...base, unestimatedTasks: 3 })).toContain(
      "3 of 8 tasks have no estimate, so the real figure is higher.",
    );
    expect(text({ ...base, taskCount: 1, unestimatedTasks: 1, estimatedMinutes: 30 }))
      .toContain("1 of 1 task has no estimate");
  });

  it("does not invent a figure when nothing is estimated", () => {
    const t = text({ ...base, estimatedMinutes: 0, unestimatedTasks: 8 });
    expect(t).toContain("Next 7 days: 8 tasks due, none with an estimate. 20h free in your study hours.");
    expect(t).not.toContain("More work than free time");
  });

  it("says zero free time as 0h, not as nothing", () => {
    expect(text({ ...base, freeMinutes: 0 })).toContain("0h free");
  });

  it("is silent when nothing is due", () => {
    expect(text({ ...base, taskCount: 0, estimatedMinutes: 0 })).toBe("");
  });
});
