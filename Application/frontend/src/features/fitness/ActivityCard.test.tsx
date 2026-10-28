// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

const api = { fetchExertion: vi.fn(), setExertionGoal: vi.fn(), logActivity: vi.fn(), deleteActivity: vi.fn() };
vi.mock("./api", () => ({
  fetchExertion: (...a: unknown[]) => api.fetchExertion(...a),
  setExertionGoal: (...a: unknown[]) => api.setExertionGoal(...a),
  logActivity: (...a: unknown[]) => api.logActivity(...a),
  deleteActivity: (...a: unknown[]) => api.deleteActivity(...a),
}));
vi.mock("../../shared/utils/dateUtils", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../shared/utils/dateUtils")>()),
  today: () => "2026-10-28",
}));

import ActivityCard from "./ActivityCard";
import { Exertion } from "./api";

/** Phase 3 items 6-7: exertion points and the weekly goal on the Fitness page. */

function exertion(over: Partial<Exertion> = {}): Exertion {
  return {
    week_start: "2026-10-26", this_week: 60, goal: 120,
    suggestion: { points: 110, reason: "Your last 4 weeks, plus 10%." },
    weeks: [],
    recent: [{ id: "a1", on_date: "2026-10-27", kind: "run", minutes: 30, points: 49, formula_version: 1, note: "loop" }],
    ...over,
  };
}

beforeEach(() => { Object.values(api).forEach((fn) => fn.mockReset()); });
afterEach(cleanup);

describe("ActivityCard", () => {
  it("shows the week against the goal, with a suggestion to take or leave", async () => {
    api.fetchExertion.mockResolvedValue(exertion());
    api.setExertionGoal.mockResolvedValue(exertion({ goal: 110 }));
    render(<ActivityCard userId="u1" />);
    expect((await screen.findByText(/points this week/)).textContent).toBe("60 points this week of 120");
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("50");
    expect(screen.getByText(/Suggested: 110\. Your last 4 weeks, plus 10%\./)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Use it" }));
    await waitFor(() => expect(api.setExertionGoal).toHaveBeenCalledWith("u1", 110));
  });

  it("logs an activity and reads the week again", async () => {
    api.fetchExertion.mockResolvedValue(exertion());
    api.logActivity.mockResolvedValue({});
    render(<ActivityCard userId="u1" />);
    fireEvent.change(await screen.findByLabelText("Kind of activity"), { target: { value: "swim" } });
    fireEvent.change(screen.getByLabelText("Minutes"), { target: { value: "45" } });
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: " laps " } });
    fireEvent.click(screen.getByRole("button", { name: "Log" }));
    await waitFor(() => expect(api.logActivity).toHaveBeenCalledWith(
      "u1", { on_date: "2026-10-28", kind: "swim", minutes: 45, note: "laps" }));
    await waitFor(() => expect(api.fetchExertion).toHaveBeenCalledTimes(2));
  });

  it("clears the goal", async () => {
    api.fetchExertion.mockResolvedValue(exertion());
    api.setExertionGoal.mockResolvedValue(exertion({ goal: null }));
    render(<ActivityCard userId="u1" />);
    fireEvent.click(await screen.findByRole("button", { name: "No goal" }));
    await waitFor(() => expect(api.setExertionGoal).toHaveBeenCalledWith("u1", null));
    await waitFor(() => expect(screen.getByText(/points this week/).textContent).toBe("60 points this week"));
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("deletes an activity only after asking", async () => {
    api.fetchExertion.mockResolvedValue(exertion());
    api.deleteActivity.mockResolvedValue({ deleted: true });
    render(<ActivityCard userId="u1" />);
    const list = await screen.findByRole("list", { name: "Recent activity" });
    fireEvent.click(within(list).getByRole("button", { name: /Delete Run/ }));
    expect(api.deleteActivity).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(api.deleteActivity).toHaveBeenCalledWith("u1", "a1"));
  });

  it("says what a suggestion needs before there's history", async () => {
    api.fetchExertion.mockResolvedValue(exertion({
      goal: null, suggestion: { points: null, reason: "Log a couple of weeks of activity for a suggestion." },
    }));
    render(<ActivityCard userId="u1" />);
    expect(await screen.findByText("Log a couple of weeks of activity for a suggestion.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Use it" })).toBeNull();
  });
});
