// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

const api = vi.hoisted(() => ({
  fetchTermReviews: vi.fn(), saveTermReview: vi.fn(), skipTermReview: vi.fn(), removeTermReview: vi.fn(),
}));
vi.mock("../termReviews", () => ({
  fetchTermReviews: (...a: unknown[]) => api.fetchTermReviews(...a),
  saveTermReview: (...a: unknown[]) => api.saveTermReview(...a),
  skipTermReview: (...a: unknown[]) => api.skipTermReview(...a),
  removeTermReview: (...a: unknown[]) => api.removeTermReview(...a),
}));

import TermReviewPanel from "./TermReviewPanel";

/** Phase 2 item 13 (D25): rate your term. */

const course = {
  course_id: "c1", code: "CPSC 221", name: "Algorithms", term_label: "Summer 2026",
  has_grade: true, can_contribute: true, review: null,
};
const answered = {
  hours_per_week: 8, difficulty: 4, clarity: 3, would_take_again: true, contribute_grade: true,
  skipped: false, created_at: "2026-10-01T00:00:00", answers_editable: true,
};

beforeEach(() => Object.values(api).forEach((fn) => fn.mockReset()));
afterEach(cleanup);

async function openWith(courses: unknown[], pending = 1) {
  api.fetchTermReviews.mockResolvedValue({ courses, pending });
  render(<TermReviewPanel userId="u1" />);
  fireEvent.click(await screen.findByRole("button", { name: pending ? "Rate them" : "See your answers" }));
  return screen.getByRole("group", { name: "CPSC 221 — Algorithms" });
}

describe("TermReviewPanel", () => {
  it("says nothing when no course finished recently, or when the read fails", async () => {
    api.fetchTermReviews.mockResolvedValue({ courses: [], pending: 0 });
    const { container, unmount } = render(<TermReviewPanel userId="u1" />);
    await waitFor(() => expect(api.fetchTermReviews).toHaveBeenCalled());
    expect(container.textContent).toBe("");
    unmount();
    api.fetchTermReviews.mockRejectedValue(new Error("down"));
    const second = render(<TermReviewPanel userId="u1" />);
    await waitFor(() => expect(api.fetchTermReviews).toHaveBeenCalledTimes(2));
    expect(second.container.textContent).toBe("");
  });

  it("says how many courses are waiting, and from which term", async () => {
    api.fetchTermReviews.mockResolvedValue({ courses: [course], pending: 1 });
    render(<TermReviewPanel userId="u1" />);
    expect(await screen.findByText("1 course from Summer 2026 to rate.")).toBeTruthy();
  });

  it("saves the four answers and the opt-in", async () => {
    api.saveTermReview.mockResolvedValue(answered);
    const form = await openWith([course]);
    fireEvent.change(within(form).getByLabelText("Hours a week for CPSC 221"), { target: { value: "8" } });
    fireEvent.click(within(within(form).getByRole("group", { name: /Difficulty/ })).getByRole("button", { name: "4" }));
    fireEvent.click(within(within(form).getByRole("group", { name: /clarity/ })).getByRole("button", { name: "3" }));
    fireEvent.click(within(form).getByRole("button", { name: "Yes" }));
    fireEvent.click(within(form).getByRole("checkbox"));
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.saveTermReview).toHaveBeenCalledWith("u1", "c1", {
      hours_per_week: 8, difficulty: 4, clarity: 3, would_take_again: true, contribute_grade: true,
    }));
  });

  it("can't offer a grade there is none of, and says why", async () => {
    const form = await openWith([{ ...course, has_grade: false }]);
    expect((within(form).getByRole("checkbox") as HTMLInputElement).disabled).toBe(true);
    expect(within(form).getByText(/no grade recorded for it yet/)).toBeTruthy();
  });

  it("skips a course", async () => {
    api.skipTermReview.mockResolvedValue({ ...answered, skipped: true });
    const form = await openWith([course]);
    fireEvent.click(within(form).getByRole("button", { name: "Skip this course" }));
    await waitFor(() => expect(api.skipTermReview).toHaveBeenCalledWith("u1", "c1"));
  });

  it("locks the answers but never the opt-in", async () => {
    const form = await openWith([{ ...course, review: { ...answered, answers_editable: false } }], 0);
    expect(within(form).getByText(/answers have locked/)).toBeTruthy();
    expect((within(form).getByLabelText("Hours a week for CPSC 221") as HTMLInputElement).disabled).toBe(true);
    expect((within(form).getByRole("checkbox") as HTMLInputElement).disabled).toBe(false);
  });

  it("asks before deleting a review, and says the grade comes out with it", async () => {
    api.removeTermReview.mockResolvedValue({ deleted: true });
    const form = await openWith([{ ...course, review: answered }], 0);
    fireEvent.click(within(form).getByRole("button", { name: "Delete my review" }));
    expect(api.removeTermReview).not.toHaveBeenCalled();
    expect(within(form).getByText(/take your grade out/)).toBeTruthy();
    fireEvent.click(within(form).getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(api.removeTermReview).toHaveBeenCalledWith("u1", "c1"));
  });

  it("never shows a count", async () => {
    await openWith([{ ...course, review: answered }], 0);
    expect(document.body.textContent).not.toMatch(/contributors|\bmedian\b|distribution of/i);
  });
});
