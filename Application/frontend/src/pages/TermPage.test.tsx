// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = { fetchTermDefaults: vi.fn(), simulateTerm: vi.fn() };
vi.mock("../features/insights/api", () => ({
  fetchTermDefaults: (...a: unknown[]) => api.fetchTermDefaults(...a),
  simulateTerm: (...a: unknown[]) => api.simulateTerm(...a),
}));
const AUTH = { user: { id: "u1" } };
vi.mock("../app/auth/AuthContext", () => ({ useAuth: () => AUTH }));

import TermPage, { spendingChange } from "./TermPage";

/** Phase 4 item 9: the 168-hour week; nothing academic until study hours are set. */

const DEFAULTS = { sleep_hours: 8, class_hours: 15, study_hours: 12, work_hours: 10, workouts_per_week: 2,
  workout_minutes: 45, overhead_hours: 3, exertion_goal: null };

function result(academic: boolean) {
  return {
    time: { rooms: [{ room: "academic", label: "Classes and study", hours: 27 }, { room: "money", label: "Work", hours: 10 },
      { room: "body", label: "Workouts", hours: 1.5 }, { room: "life", label: "Sleep and everything else", hours: 77 }],
      total: 115.5, fits: true, short_by: 0, spare: 52.5 },
    money: null, body: { points_per_week: 60, goal: null, meets_goal: null },
    academic: academic ? { study_hours: 12, estimated_hours: 12, coverage: 100, reading: "12 hours covers the 12 your tasks are estimated at.",
      bands: [{ code: "CPSC 310", current: 71, best: 87, worst: 29 }] } : null,
    assumptions: ["A week is 168 hours."],
  };
}

beforeEach(() => {
  api.fetchTermDefaults.mockReset().mockResolvedValue(DEFAULTS);
  api.simulateTerm.mockReset().mockImplementation((_u: string, body: { study_hours: number | null }) =>
    Promise.resolve(result(body.study_hours !== null)));
});
afterEach(cleanup);

describe("TermPage", () => {
  it("starts from your figures with study hours not set, so nothing academic shows", async () => {
    render(<TermPage />);

    await waitFor(() => expect(api.simulateTerm).toHaveBeenCalled());
    expect(api.simulateTerm.mock.calls[0][1]).toMatchObject({ study_hours: null, work_hours: 10, class_hours: 15 });
    expect(await screen.findByText("Fits, with 52.5 hours spare")).toBeTruthy();
    expect(screen.queryByText("Study")).toBeNull();
  });

  it("shows what set study hours cover, beside the bands as they stand", async () => {
    render(<TermPage />);
    fireEvent.click(await screen.findByRole("checkbox", { name: "Set my study hours" }));

    await waitFor(() => expect(api.simulateTerm.mock.lastCall?.[1].study_hours).toBe(12));
    expect(await screen.findByText(/covers the 12/)).toBeTruthy();
    expect(screen.getByText("CPSC 310: 29–87, now 71")).toBeTruthy();
  });

  it("sends the work slider's hours", async () => {
    render(<TermPage />);
    const work = await screen.findByRole("slider", { name: "Work a week" });

    fireEvent.change(work, { target: { value: "25" } });

    await waitFor(() => expect(api.simulateTerm.mock.lastCall?.[1].work_hours).toBe(25));
  });
});

describe("spendingChange", () => {
  it("reads as a change, so zero never looks like no spending", () => {
    expect(spendingChange(0)).toBe("no change");
    expect(spendingChange(250)).toBe("+$250");
    expect(spendingChange(-75)).toBe("\u2212$75");
  });
});
