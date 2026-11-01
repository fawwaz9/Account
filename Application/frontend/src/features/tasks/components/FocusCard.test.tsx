// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = { fetchFocus: vi.fn(), startFocus: vi.fn(), stopFocus: vi.fn() };
vi.mock("../focusApi", () => ({
  fetchFocus: (...a: unknown[]) => api.fetchFocus(...a),
  startFocus: (...a: unknown[]) => api.startFocus(...a),
  stopFocus: (...a: unknown[]) => api.stopFocus(...a),
}));

import FocusCard from "./FocusCard";

/** Phase 4 item 4: a study timer tagged per course. */

const IDLE = {
  running: null, total_this_week: 80,
  courses: [
    { course_id: "c1", course_code: "CPSC 310", minutes_this_week: 60, minutes_term: 600, grade: 82 },
    { course_id: "c2", course_code: "MATH 200", minutes_this_week: 20, minutes_term: 120, grade: 68 },
    { course_id: null, course_code: "No course", minutes_this_week: 0, minutes_term: 0, grade: null },
  ],
};

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  api.fetchFocus.mockResolvedValue(IDLE);
  api.startFocus.mockResolvedValue({});
  api.stopFocus.mockResolvedValue({});
});
afterEach(cleanup);

describe("FocusCard", () => {
  it("starts a session on the chosen course", async () => {
    render(<FocusCard userId="u1" />);
    fireEvent.change(await screen.findByRole("combobox", { name: "Course to focus on" }), { target: { value: "c2" } });

    fireEvent.click(screen.getByRole("button", { name: "Start" }));

    await waitFor(() => expect(api.startFocus).toHaveBeenCalledWith("u1", "c2"));
  });

  it("shows the running session and stops it", async () => {
    api.fetchFocus.mockResolvedValue({ ...IDLE, running: { id: "s1", course_id: "c1", course_code: "CPSC 310",
      started_at: new Date(Date.now() - 25 * 60000).toISOString().slice(0, 19), ended_at: null, minutes: null } });
    render(<FocusCard userId="u1" />);

    expect(await screen.findByText(/25m/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));

    await waitFor(() => expect(api.stopFocus).toHaveBeenCalledWith("u1"));
  });

  it("lists this week's minutes per course and draws hours against grade", async () => {
    render(<FocusCard userId="u1" />);

    expect(await screen.findByText("1h")).toBeTruthy();
    expect(screen.getByText("1h 20m")).toBeTruthy();
    expect(screen.getByRole("img", { name: /Hours focused this term against each course's grade/ })).toBeTruthy();
  });

  it("draws no chart with fewer than two courses to compare", async () => {
    api.fetchFocus.mockResolvedValue({ ...IDLE, courses: [IDLE.courses[0]] });
    render(<FocusCard userId="u1" />);

    await screen.findByText("Focus");
    expect(screen.queryByRole("img")).toBeNull();
  });
});
