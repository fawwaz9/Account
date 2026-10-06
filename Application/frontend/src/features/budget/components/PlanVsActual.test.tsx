// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = { fetchPlanReview: vi.fn(), savePlan: vi.fn() };
vi.mock("../api", () => ({
  fetchPlanReview: (...a: unknown[]) => api.fetchPlanReview(...a),
  savePlan: (...a: unknown[]) => api.savePlan(...a),
}));

import PlanVsActual from "./PlanVsActual";
import { formatMoney } from "../money";

const may = {
  month: "2026-05-01", plan_saved_on: "2026-04-20",
  planned_in: 2000, planned_out: 1500, planned_end: 1400,
  actual_in: 2100, actual_out: 1775, actual_end: 1325, tuition_out: 900,
};

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
});
afterEach(cleanup);

describe("PlanVsActual", () => {
  it("before any save, says what saving is for", async () => {
    api.fetchPlanReview.mockResolvedValue({ latest: null, months: [] });
    render(<PlanVsActual userId="u1" nonce={0} />);
    expect((await screen.findByRole("status")).textContent).toContain("Save the plan to see");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("says when the comparison starts, from the month after the save", async () => {
    api.fetchPlanReview.mockResolvedValue({
      latest: { id: "p1", saved_on: "2026-12-14", starts_on: "2026-12-14", ends_on: "2027-04-30" },
      months: [],
    });
    render(<PlanVsActual userId="u1" nonce={0} />);
    await waitFor(() => expect(screen.getByRole("status").textContent).toMatch(/from Jan.*2027/));
  });

  it("shows each month's actual over the plan, flags the worse, and names tuition", async () => {
    api.fetchPlanReview.mockResolvedValue({
      latest: { id: "p1", saved_on: "2026-04-20", starts_on: "2026-04-20", ends_on: "2027-04-30" },
      months: [may],
    });
    render(<PlanVsActual userId="u1" nonce={0} />);
    const table = await screen.findByRole("table");
    const cells = Array.from(table.querySelectorAll("tbody td"));
    expect(cells.map((cell) => cell.textContent)).toEqual([
      `${formatMoney(2100)}plan ${formatMoney(2000)}`,
      `${formatMoney(1775)}plan ${formatMoney(1500)}`,
      `${formatMoney(1325)}plan ${formatMoney(1400)}`,
    ]);
    // Out over the plan and the balance under it are the worse; more in is not.
    expect(cells.map((cell) => Boolean(cell.querySelector(".yearPlanNegative")))).toEqual([false, true, true]);
    expect(table.textContent).toContain(`includes ${formatMoney(900)} tuition, which the plan leaves out`);
  });

  it("saves, then reads again; a failure is said", async () => {
    api.fetchPlanReview.mockResolvedValue({ latest: null, months: [] });
    api.savePlan.mockRejectedValueOnce(new Error("Server unavailable")).mockResolvedValueOnce({});
    render(<PlanVsActual userId="u1" nonce={0} />);
    const button = await screen.findByRole("button", { name: "Save as my plan" });

    fireEvent.click(button);
    expect((await screen.findByRole("alert")).textContent).toBe("Server unavailable");

    fireEvent.click(button);
    await waitFor(() => expect(api.fetchPlanReview).toHaveBeenCalledTimes(2));
    expect(api.savePlan).toHaveBeenCalledWith("u1");
  });
});
