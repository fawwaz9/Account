// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const fetchRequiredFinal = vi.fn();
vi.mock("../api", () => ({ fetchRequiredFinal: (...a: unknown[]) => fetchRequiredFinal(...a) }));

import RequiredFinalPanel, { finalStillAhead } from "./RequiredFinalPanel";
import { CourseDetail, GradeCategory } from "../types";

function course(overrides: Partial<CourseDetail> = {}): CourseDetail {
  return {
    id: "c1",
    code: "CPSC 221",
    name: "Data Structures",
    year: 2026,
    semester: "Fall",
    credits: 4,
    required: true,
    professor: null,
    final_grade: 0,
    category_weights: { [GradeCategory.MIDTERM]: 40, [GradeCategory.FINAL]: 60 },
    average: 72,
    target_grade: 85,
    letter_grade: "B",
    grade_points: 3,
    grades: [],
    start_date: null,
    end_date: null,
    no_final: false,
    transfer_credit: false,
    archived: false,
    term_bucket: "current",
    links: [],
    category_averages: {},
    category_points: {},
    ...overrides,
  } as CourseDetail;
}

const finalMark = {
  id: "g1", name: "Final", score: 80, max_score: 100, category: GradeCategory.FINAL,
} as CourseDetail["grades"][number];

function show(c: CourseDetail, onTryAnother = vi.fn()) {
  return render(
    <RequiredFinalPanel userId="u1" course={c} defaultTarget={80} nonce={0} onTryAnother={onTryAnother} />,
  );
}

beforeEach(() => {
  fetchRequiredFinal.mockReset();
});
afterEach(cleanup);

describe("RequiredFinalPanel", () => {
  it("answers against the course's own target, without being asked", async () => {
    fetchRequiredFinal.mockResolvedValue({ needed: 78.5, possible: true, unfinished_categories: [] });
    show(course());
    expect(await screen.findByText("You need 78.5%.")).toBeTruthy();
    expect(screen.getByText("for 85%")).toBeTruthy();
    expect(fetchRequiredFinal).toHaveBeenCalledWith("u1", "c1", 85);
  });

  it("falls back to the account default when the course has no target", async () => {
    fetchRequiredFinal.mockResolvedValue({ needed: 70, possible: true, unfinished_categories: [] });
    show(course({ target_grade: null }));
    expect(await screen.findByText("for 80%")).toBeTruthy();
    expect(fetchRequiredFinal).toHaveBeenCalledWith("u1", "c1", 80);
  });

  it("says plainly when the target is secured, or out of reach", async () => {
    fetchRequiredFinal.mockResolvedValue({ needed: -4, possible: false, unfinished_categories: [] });
    const { unmount } = show(course());
    expect(await screen.findByText("85% is already secured. Any final keeps it.")).toBeTruthy();
    unmount();

    fetchRequiredFinal.mockResolvedValue({ needed: 112, possible: false, unfinished_categories: [] });
    show(course());
    expect(await screen.findByText("Out of reach: it would take 112%.")).toBeTruthy();
  });

  it("names the categories the figure cannot count yet", async () => {
    fetchRequiredFinal.mockResolvedValue({ needed: 60, possible: true, unfinished_categories: ["Lab", "Quiz"] });
    show(course());
    expect(await screen.findByText("Assumes nothing yet for lab, quiz")).toBeTruthy();
  });

  it("opens the calculator for a different target", async () => {
    fetchRequiredFinal.mockResolvedValue({ needed: 60, possible: true, unfinished_categories: [] });
    const onTryAnother = vi.fn();
    show(course(), onTryAnother);
    fireEvent.click(await screen.findByRole("button", { name: "Try another target" }));
    expect(onTryAnother).toHaveBeenCalled();
  });

  it("shows nothing while the answer is on its way", () => {
    fetchRequiredFinal.mockReturnValue(new Promise(() => {}));
    const { container } = show(course());
    expect(container.innerHTML).toBe("");
  });

  it("shows nothing if the answer fails", async () => {
    fetchRequiredFinal.mockRejectedValue(new Error("500"));
    const { container } = show(course());
    await waitFor(() => expect(fetchRequiredFinal).toHaveBeenCalled());
    await Promise.resolve();
    expect(container.innerHTML).toBe("");
  });

  it("stays silent, and asks nothing, when the final is not still ahead", () => {
    for (const c of [
      course({ term_bucket: "past" }),
      course({ term_bucket: "future" }),
      course({ no_final: true }),
      course({ transfer_credit: true }),
      course({ category_weights: { [GradeCategory.MIDTERM]: 100 } }),
      course({ grades: [finalMark] }),
    ]) {
      expect(finalStillAhead(c)).toBe(false);
      const { container, unmount } = show(c);
      expect(container.innerHTML).toBe("");
      unmount();
    }
    expect(fetchRequiredFinal).not.toHaveBeenCalled();
  });

  it("an unmarked final grade row does not count as a mark", () => {
    expect(finalStillAhead(course({ grades: [{ ...finalMark, score: null }] }))).toBe(true);
  });
});
