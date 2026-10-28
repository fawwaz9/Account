// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = { fetchOutline: vi.fn(), offerOutline: vi.fn(), withdrawOutlineOffer: vi.fn(), applyOutline: vi.fn() };
vi.mock("../api", () => ({
  fetchOutline: (...a: unknown[]) => api.fetchOutline(...a),
  offerOutline: (...a: unknown[]) => api.offerOutline(...a),
  withdrawOutlineOffer: (...a: unknown[]) => api.withdrawOutlineOffer(...a),
  applyOutline: (...a: unknown[]) => api.applyOutline(...a),
}));

import CourseOutline from "./CourseOutline";
import { GradeCategory, OutlineStatus } from "../types";

/** Phase 3 item 2: shared course outlines on the course page (D12). */

function status(over: Partial<OutlineStatus> = {}): OutlineStatus {
  return {
    course_key: "CPSC 221", term_code: "2026W1", can_offer: true, offer_blocked: null, offer: null, shared: null,
    can_apply: false, ...over,
  };
}

const shared = {
  approved_at: "2026-10-20T00:00:00",
  outline: {
    weights: { Assignment: 40, Final: 60 },
    assessments: [{ name: "Midterm 1", category: GradeCategory.MIDTERM, due_date: "2026-10-15" }],
  },
};

const onApplied = vi.fn();
function show() {
  return render(<CourseOutline userId="u1" courseId="c1" nonce={0} onApplied={onApplied} />);
}

beforeEach(() => { Object.values(api).forEach((fn) => fn.mockReset()); onApplied.mockReset(); });
afterEach(cleanup);

describe("CourseOutline", () => {
  it("offers to fill an empty course from a reviewed outline, previewed first", async () => {
    api.fetchOutline.mockResolvedValue(status({ shared, can_apply: true }));
    api.applyOutline.mockResolvedValue(status({ shared, can_apply: false }));
    show();
    expect(await screen.findByText(/2 categories, 1 assessments, no marks/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect(screen.getByText("Midterm 1 · Midterm · due 2026-10-15")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Use it" }));
    await waitFor(() => expect(onApplied).toHaveBeenCalled());
    expect(api.applyOutline).toHaveBeenCalledWith("u1", "c1");
  });

  it("offers this course's outline, then says it awaits review and can be taken back", async () => {
    api.fetchOutline.mockResolvedValueOnce(status()).mockResolvedValueOnce(status());
    api.offerOutline.mockResolvedValue(status({ offer: { status: "pending", created_at: "2026-10-28T00:00:00" } }));
    api.withdrawOutlineOffer.mockResolvedValue({ deleted: true });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Offer outline" }));
    expect(await screen.findByText(/waiting for review/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Take back" }));
    await waitFor(() => expect(api.withdrawOutlineOffer).toHaveBeenCalledWith("u1", "c1"));
    expect(await screen.findByRole("button", { name: "Offer outline" })).toBeTruthy();
  });

  it("says where an approved offer stands", async () => {
    api.fetchOutline.mockResolvedValue(status({ offer: { status: "accepted", created_at: "x" } }));
    show();
    expect(await screen.findByText(/classmates in this course and term can use it/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Take back" })).toBeNull();
  });

  it("shows why a fill was refused", async () => {
    api.fetchOutline.mockResolvedValue(status({ shared, can_apply: true }));
    api.applyOutline.mockRejectedValue(new Error("This course already has grades"));
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Use it" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/already has grades/);
    expect(onApplied).not.toHaveBeenCalled();
  });

  it("is silent when nothing can be offered or used", async () => {
    api.fetchOutline.mockResolvedValue(status({ can_offer: false, offer_blocked: "Transfer credit" }));
    const { container } = show();
    await waitFor(() => expect(api.fetchOutline).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });
});
