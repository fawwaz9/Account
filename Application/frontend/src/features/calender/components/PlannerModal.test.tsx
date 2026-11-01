// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = { fetchWeekPlan: vi.fn(), acceptWeekPlan: vi.fn() };
vi.mock("../plannerApi", () => ({
  fetchWeekPlan: (...a: unknown[]) => api.fetchWeekPlan(...a),
  acceptWeekPlan: (...a: unknown[]) => api.acceptWeekPlan(...a),
}));

import PlannerModal from "./PlannerModal";

/** Phase 4 item 2: each block with why, ticked by default; what didn't fit, said. */

const PLAN = {
  starts_on: "2099-11-02", ends_on: "2099-11-08",
  blocks: [
    { task_id: "t1", title: "Essay", course_code: "ENGL 110", due_date: "2099-11-04", on_date: "2099-11-02",
      starts_at: "09:00:00", ends_at: "11:00:00", minutes: 120, reason: "The first free time before it's due Wednesday." },
    { task_id: "t2", title: "Lab", course_code: null, due_date: "2099-11-03", on_date: "2099-11-02",
      starts_at: "13:00:00", ends_at: "14:00:00", minutes: 60, reason: "The first free time before it's due tomorrow." },
  ],
  unplaced: [{ task_id: "t3", title: "Project", due_date: "2099-11-03", minutes_needed: 180, minutes_short: 120,
    reason: "Only 60 of 180 minutes are free before it's due tomorrow." }],
  assumptions: ["No block runs longer than 2 hours."],
};

beforeEach(() => {
  api.fetchWeekPlan.mockReset().mockResolvedValue(PLAN);
  api.acceptWeekPlan.mockReset().mockResolvedValue({ created: 1 });
});
afterEach(cleanup);

function open() {
  render(<PlannerModal userId="u1" onClose={() => {}} />);
}

describe("PlannerModal", () => {
  it("shows each block with why, all ticked", async () => {
    open();

    expect(await screen.findByText("The first free time before it's due Wednesday.")).toBeTruthy();
    expect(screen.getAllByRole("checkbox").every((c) => (c as HTMLInputElement).checked)).toBe(true);
    expect(screen.getByRole("button", { name: "Add 2 to calendar" })).toBeTruthy();
  });

  it("says what didn't fit, and by how much", async () => {
    open();

    expect(await screen.findByText(/Only 60 of 180 minutes/)).toBeTruthy();
    expect(screen.getByText(/2h short/)).toBeTruthy();
  });

  it("adds only the ticked blocks", async () => {
    open();
    fireEvent.click(await screen.findByRole("checkbox", { name: /Add Lab/ }));

    fireEvent.click(screen.getByRole("button", { name: "Add 1 to calendar" }));

    await waitFor(() => expect(api.acceptWeekPlan).toHaveBeenCalled());
    const [, blocks] = api.acceptWeekPlan.mock.calls[0];
    expect(blocks.map((b: { task_id: string }) => b.task_id)).toEqual(["t1"]);
    expect(await screen.findByText("1 block added to your calendar.")).toBeTruthy();
  });

  it("says so when nothing needs planning", async () => {
    api.fetchWeekPlan.mockResolvedValue({ ...PLAN, blocks: [], unplaced: [] });
    open();

    expect(await screen.findByText("Nothing due in the next week needs planning.")).toBeTruthy();
  });
});
