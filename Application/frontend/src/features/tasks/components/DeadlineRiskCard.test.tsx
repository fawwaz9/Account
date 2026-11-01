// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import DeadlineRiskCard from "./DeadlineRiskCard";
import { DeadlineRisk, RiskDeadline } from "../types";

/** Phase 4 item 3: your pace against what each due date needs; quiet until it knows you. */

function deadline(over: Partial<RiskDeadline> = {}): RiskDeadline {
  return {
    due_date: "2099-01-01", tasks: 1, titles: ["Essay draft"], own_minutes: 240, minutes_by_then: 240,
    days_left: 3, required_minutes_per_day: 80, at_risk: true, shortfall_minutes: 135,
    ...over,
  };
}

function risk(over: Partial<DeadlineRisk> = {}): DeadlineRisk {
  return {
    ready: true, history_days: 28, needed_days: 14, counted_tasks: 14, needed_tasks: 5, window_days: 28,
    velocity_minutes_per_day: 35, estimate_ratio: null, unestimated_open: 0, horizon_days: 21,
    deadlines: [deadline()],
    ...over,
  };
}

afterEach(cleanup);

describe("DeadlineRiskCard", () => {
  it("names each deadline at risk with the pace it needs and the shortfall", () => {
    render(<DeadlineRiskCard risk={risk()} />);

    expect(screen.getByText("1 deadline at risk")).toBeTruthy();
    expect(screen.getByText(/about 35m a day/)).toBeTruthy();
    expect(screen.getByText("Essay draft")).toBeTruthy();
    expect(screen.getByText(/needs 1h 20m a day for 3 days; about 2h 15m short/)).toBeTruthy();
  });

  it("says when earlier work makes up part of a deadline", () => {
    render(<DeadlineRiskCard risk={risk({ deadlines: [deadline({ own_minutes: 60 })] })} />);

    expect(screen.getByText(/with what's due before it/)).toBeTruthy();
  });

  it("leaves out deadlines that are on pace, and says when all of them are", () => {
    render(<DeadlineRiskCard risk={risk({ deadlines: [deadline({ at_risk: false, titles: ["Fine"] })] })} />);

    expect(screen.getByText("On pace")).toBeTruthy();
    expect(screen.queryByText("Fine")).toBeNull();
    expect(screen.getByText(/Everything due in the next 21 days fits/)).toBeTruthy();
  });

  it("is quiet before it knows your pace, and says how close it is", () => {
    render(<DeadlineRiskCard risk={risk({ ready: false, history_days: 6, counted_tasks: 3, deadlines: [],
      velocity_minutes_per_day: null })} />);

    expect(screen.queryByText(/at risk/)).toBeNull();
    expect(screen.getByText(/6 of 14 days, 3 of 5 finished tasks/)).toBeTruthy();
  });

  it("says nothing at all with no finished work to learn from", () => {
    const { container } = render(<DeadlineRiskCard risk={risk({ ready: false, history_days: 0, counted_tasks: 0,
      deadlines: [], velocity_minutes_per_day: null })} />);

    expect(container.textContent).toBe("");
  });

  it("owns up to tasks it can't count", () => {
    render(<DeadlineRiskCard risk={risk({ unestimated_open: 2 })} />);

    expect(screen.getByText(/2 tasks have no estimate, so they aren't counted/)).toBeTruthy();
  });
});
