// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = { fetchGradeScenario: vi.fn() };
vi.mock("../api", () => ({
  fetchGradeScenario: (...a: unknown[]) => api.fetchGradeScenario(...a),
}));

import GradeScenarioModal from "./GradeScenarioModal";
import { GradeScenario, GradeScenarioIn } from "../types";

/** Phase 4 item 10: sliders per unmarked assessment, the projection from the server. */

function answer(body: GradeScenarioIn, over: Partial<GradeScenario> = {}): GradeScenario {
  const final = body.scores["g-final"];
  return {
    course_id: "c1", current: 71, projected: final === undefined ? 69.88 : 78.06, letter: "B+",
    best: 87.28, worst: 29.28, assume: body.assume,
    items: [
      { grade_id: "g-a2", name: "Assignment 2", category: "Assignment", max_score: 100,
        due_date: "2026-11-14", percent: body.scores["g-a2"] ?? body.assume, set: "g-a2" in body.scores },
      { grade_id: "g-final", name: "Final exam", category: "Final", max_score: 100,
        due_date: "2026-12-12", percent: final ?? body.assume, set: final !== undefined },
    ],
    empty_categories: [], assumptions: ["Everything you haven't set scores 71%."],
    ...over,
  };
}

beforeEach(() => {
  api.fetchGradeScenario.mockReset();
  api.fetchGradeScenario.mockImplementation((_u: string, _c: string, body: GradeScenarioIn) =>
    Promise.resolve(answer(body)));
});
afterEach(cleanup);

function open() {
  render(<GradeScenarioModal userId="u1" courseId="c1" courseCode="CPSC 310" current={70.6} onClose={() => {}} />);
}

describe("GradeScenarioModal", () => {
  it("starts everything else at the grade now, rounded, and shows the projection", async () => {
    open();

    await waitFor(() => expect(screen.getByText("69.88%")).toBeTruthy());
    expect(api.fetchGradeScenario).toHaveBeenLastCalledWith("u1", "c1", { assume: 71, scores: {} });
    expect(screen.getByText("B+")).toBeTruthy();
  });

  it("sends a slider's score for that assessment only", async () => {
    open();
    await screen.findByRole("slider", { name: "Score for Final exam" });

    fireEvent.change(screen.getByRole("slider", { name: "Score for Final exam" }), { target: { value: "90" } });

    await waitFor(() => expect(screen.getByText("78.06%")).toBeTruthy());
    expect(api.fetchGradeScenario).toHaveBeenLastCalledWith("u1", "c1", { assume: 71, scores: { "g-final": 90 } });
  });

  it("puts an assessment back with everything else", async () => {
    open();
    fireEvent.change(await screen.findByRole("slider", { name: "Score for Final exam" }), { target: { value: "90" } });
    await screen.findByText("78.06%");

    fireEvent.click(screen.getByRole("button", { name: "Put Final exam back with everything else" }));

    await waitFor(() => expect(api.fetchGradeScenario).toHaveBeenLastCalledWith("u1", "c1", { assume: 71, scores: {} }));
  });

  it("lets only the newest answer land", async () => {
    let releaseOld: (value: GradeScenario) => void = () => {};
    api.fetchGradeScenario
      .mockImplementationOnce(() => new Promise<GradeScenario>((resolve) => { releaseOld = resolve; }))
      .mockImplementation((_u: string, _c: string, body: GradeScenarioIn) => Promise.resolve(answer(body)));
    open();
    await waitFor(() => expect(api.fetchGradeScenario).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByRole("slider", { name: "Score for everything you haven't set" }),
      { target: { value: "40" } });
    await waitFor(() => expect(api.fetchGradeScenario).toHaveBeenCalledTimes(2));
    await screen.findByText("69.88%");

    releaseOld(answer({ assume: 71, scores: {} }, { projected: 11.11 }));
    await new Promise((r) => setTimeout(r, 0));

    expect(screen.queryByText("11.11%")).toBeNull();
  });

  it("says what it assumed, and where the course can still finish", async () => {
    open();

    await screen.findByText("Everything you haven't set scores 71%.");
    expect(screen.getByText(/anywhere from 29.28% to 87.28%/)).toBeTruthy();
  });
});
