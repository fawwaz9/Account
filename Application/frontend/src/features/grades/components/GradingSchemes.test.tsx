// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = {
  fetchSchemes: vi.fn(), createScheme: vi.fn(), updateScheme: vi.fn(), deleteScheme: vi.fn(), setCountingScheme: vi.fn(),
};
vi.mock("../api", () => ({
  fetchSchemes: (...a: unknown[]) => api.fetchSchemes(...a),
  createScheme: (...a: unknown[]) => api.createScheme(...a),
  updateScheme: (...a: unknown[]) => api.updateScheme(...a),
  deleteScheme: (...a: unknown[]) => api.deleteScheme(...a),
  setCountingScheme: (...a: unknown[]) => api.setCountingScheme(...a),
}));

import GradingSchemes from "./GradingSchemes";
import { CourseDetail, GradeCategory, SchemeComparison } from "../types";

const course = {
  id: "c1", code: "CPSC 210",
  category_weights: { [GradeCategory.MIDTERM]: 40, [GradeCategory.FINAL]: 60, [GradeCategory.QUIZ]: 0 },
} as unknown as CourseDetail;

const comparison: SchemeComparison = {
  current: { id: null, label: "As set on the course", average: 78, components: [], lines: [] },
  schemes: [{
    id: "s1", label: "Final replaces midterm", average: 80,
    components: [
      { category: GradeCategory.MIDTERM, weight: 40, drop_lowest: 0, replace_with: GradeCategory.FINAL },
      { category: GradeCategory.QUIZ, weight: 0, drop_lowest: 2, replace_with: null },
    ],
    lines: [
      { category: GradeCategory.MIDTERM, weight: 40, average: 80, dropped: 0, replaced_by: GradeCategory.FINAL },
      { category: GradeCategory.QUIZ, weight: 0, average: null, dropped: 0, replaced_by: null },
    ],
  }],
  best_id: "s1",
};

function show() {
  return render(<GradingSchemes userId="u1" course={course} nonce={0} />);
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.fetchSchemes.mockResolvedValue(comparison);
});
afterEach(cleanup);

describe("GradingSchemes", () => {
  it("compares the course's own figure with each scheme, the better one marked", async () => {
    show();
    expect(await screen.findByText("Final replaces midterm")).toBeTruthy();
    expect(screen.getByText("As set on the course")).toBeTruthy();
    expect(screen.getByText("higher")).toBeTruthy();
    expect(screen.getByText("Final counted instead")).toBeTruthy();
    expect(screen.getByText("nothing marked")).toBeTruthy();
  });

  it("offers only the way to add one when there are none", async () => {
    api.fetchSchemes.mockResolvedValue({ ...comparison, schemes: [], best_id: null });
    show();
    expect(await screen.findByRole("button", { name: "Add another grading scheme" })).toBeTruthy();
    expect(screen.queryByText("As set on the course")).toBeNull();
  });

  it("a new scheme starts from the course's own weights", async () => {
    api.createScheme.mockResolvedValue({});
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Add another grading scheme" }));
    expect((screen.getByLabelText("Midterm weight") as HTMLInputElement).value).toBe("40");
    expect(screen.queryByLabelText("Quiz weight")).toBeNull(); // zero weight on the course
    fireEvent.change(screen.getByLabelText("Midterm weight"), { target: { value: "20" } });
    fireEvent.change(screen.getByLabelText("Final weight"), { target: { value: "80" } });
    fireEvent.click(screen.getByRole("button", { name: "Save scheme" }));
    await waitFor(() => expect(api.createScheme).toHaveBeenCalled());
    const [, courseId, body] = api.createScheme.mock.calls[0];
    expect(courseId).toBe("c1");
    expect(body.components.map((c: { weight: number }) => c.weight)).toEqual([20, 80]);
  });

  it("editing starts from the rules as written, not what they did so far", async () => {
    api.updateScheme.mockResolvedValue({});
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    expect((screen.getByLabelText("Quiz drop lowest") as HTMLInputElement).value).toBe("2");
    expect((screen.getByLabelText("Midterm replaced by") as HTMLSelectElement).value).toBe("Final");
    fireEvent.click(screen.getByRole("button", { name: "Save scheme" }));
    await waitFor(() => expect(api.updateScheme).toHaveBeenCalled());
    const [, , schemeId, body] = api.updateScheme.mock.calls[0];
    expect(schemeId).toBe("s1");
    expect(body.components[1].drop_lowest).toBe(2);
  });

  it("asks before removing, and removes nothing on cancel", async () => {
    api.deleteScheme.mockResolvedValue({ deleted: true });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Remove" }));
    expect(screen.getByText(/will be removed. Your marks and the course's own weights are not touched/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /cancel|keep/i }));
    expect(api.deleteScheme).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Remove" }).at(-1)!);
    await waitFor(() => expect(api.deleteScheme).toHaveBeenCalledWith("u1", "c1", "s1"));
  });

  it("says why a scheme couldn't be saved", async () => {
    api.createScheme.mockRejectedValue(new Error("Each category can appear once in a scheme"));
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Add another grading scheme" }));
    fireEvent.click(screen.getByRole("button", { name: "Save scheme" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Each category can appear once in a scheme");
  });

  it("makes a scheme the grade, says so while switching, and tells the page", async () => {
    let finish: (value: SchemeComparison) => void = () => {};
    api.setCountingScheme.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const changed = vi.fn();
    render(<GradingSchemes userId="u1" course={course} nonce={0} onCountingChanged={changed} />);
    const [toScheme] = await screen.findAllByRole("button", { name: "Count as grade" });
    expect(screen.getAllByRole("button", { name: "Count as grade" })).toHaveLength(1);  // own weights already count
    fireEvent.click(toScheme);
    expect(screen.getByRole("button", { name: "Switching…" })).toBeTruthy();
    expect(api.setCountingScheme).toHaveBeenCalledWith("u1", "c1", "s1");
    finish({ ...comparison, counting_id: "s1" });
    expect(await screen.findByText("Counting as your grade: Final replaces midterm")).toBeTruthy();
    expect(changed).toHaveBeenCalledTimes(1);
    expect(screen.getByText("counts")).toBeTruthy();
  });

  it("puts the course's own weights back from the first row", async () => {
    api.fetchSchemes.mockResolvedValue({ ...comparison, counting_id: "s1" });
    api.setCountingScheme.mockResolvedValue({ ...comparison, counting_id: null });
    show();
    expect(await screen.findByText("Counting as your grade: Final replaces midterm")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Count as grade" }));
    await waitFor(() => expect(api.setCountingScheme).toHaveBeenCalledWith("u1", "c1", null));
    await waitFor(() => expect(screen.queryByText(/Counting as your grade/)).toBeNull());
  });

  it("says when switching failed", async () => {
    api.setCountingScheme.mockRejectedValue(new Error("500"));
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Count as grade" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Couldn't change which scheme counts");
  });

  it("warns that removing the counting scheme puts the own weights back", async () => {
    api.fetchSchemes.mockResolvedValue({ ...comparison, counting_id: "s1" });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Remove" }));
    expect(await screen.findByText(/is counting as your grade/)).toBeTruthy();
  });
});
