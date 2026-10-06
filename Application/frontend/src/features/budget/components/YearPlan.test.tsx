// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const fetchPlan = vi.fn();
// The plan-against-actual section under the plan reads too; it has its own tests.
vi.mock("../api", () => ({
  fetchPlan: (...a: unknown[]) => fetchPlan(...a),
  fetchPlanReview: () => Promise.resolve({ latest: null, months: [] }),
  savePlan: () => Promise.resolve({}),
}));
vi.mock("../../../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));

import YearPlan from "./YearPlan";
import { AnnualPlan, PlanGoal } from "../types";

function planned(overrides: Partial<AnnualPlan> = {}): AnnualPlan {
  return {
    starts_on: "2026-10-14",
    ends_on: "2027-04-30",
    starting_balance: 3000,
    months: [
      { month: "2026-10-01", money_in: 0, money_out: 600, end_balance: 2400 },
      { month: "2026-11-01", money_in: 1295, money_out: 600, end_balance: 3095 },
      { month: "2026-12-01", money_in: 0, money_out: 3700, end_balance: -605 },
    ],
    ending_balance: -605,
    lowest_balance: -605,
    lowest_on: "2026-12-31",
    goal: null,
    assumptions: ["Standing instructions run as scheduled."],
    ...overrides,
  };
}

const goal: PlanGoal = {
  target: 2000, target_on: "2027-04-30", base_end_balance: -1200, shortfall: 3200,
  job_name: "Bookstore", net_hourly: 20, weeks: 28.3, extra_hours_per_week: 6,
  scenarios: [
    { extra_hours_per_week: 0, end_balance: -1200 },
    { extra_hours_per_week: 4, end_balance: 1062.86 },
  ],
};

async function show(first: AnnualPlan | Error = planned()) {
  if (first instanceof Error) fetchPlan.mockRejectedValueOnce(first);
  else fetchPlan.mockResolvedValueOnce(first);
  const view = render(<YearPlan nonce={0} />);
  await waitFor(() => expect(fetchPlan).toHaveBeenCalledWith("u1"));
  return view;
}

function ask(amount: string) {
  fireEvent.change(screen.getByLabelText("Balance to reach"), { target: { value: amount } });
  fireEvent.click(screen.getByRole("button", { name: "Work it out" }));
}

beforeEach(() => {
  fetchPlan.mockReset();
});
afterEach(cleanup);

describe("YearPlan", () => {
  it("lays the year out as months with a running balance", async () => {
    const { container } = await show();
    expect(await screen.findByText("$3,095.00")).toBeTruthy();
    expect(screen.getAllByRole("row")).toHaveLength(4); // header + 3 months
    expect(container.querySelector(".yearPlanNegative")?.textContent).toBe("−$605.00") // formatMoney uses a true minus sign;
  });

  it("turns a target into extra hours a week, with scenarios", async () => {
    await show();
    await screen.findByText("$3,095.00");
    fetchPlan.mockResolvedValueOnce(planned({ goal }));
    ask("2000");
    expect(await screen.findByText("6 extra hours a week")).toBeTruthy();
    expect(fetchPlan).toHaveBeenLastCalledWith("u1", 2000, undefined);
    expect(screen.getByText("+4 h a week")).toBeTruthy();
    expect(screen.getByText("$1,062.86")).toBeTruthy();
  });

  it("acknowledges the press while it works", async () => {
    await show();
    await screen.findByText("$3,095.00");
    let finish: (value: AnnualPlan) => void = () => {};
    fetchPlan.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    ask("2000");
    const button = screen.getByRole("button", { name: "Working…" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    finish(planned({ goal }));
    expect(await screen.findByRole("button", { name: "Work it out" })).toBeTruthy();
  });

  it("passes a chosen date along", async () => {
    await show();
    await screen.findByText("$3,095.00");
    fetchPlan.mockResolvedValueOnce(planned({ goal }));
    fireEvent.change(screen.getByLabelText("Reach it by"), { target: { value: "2026-12-31" } });
    ask("3000");
    await screen.findByText("6 extra hours a week");
    expect(fetchPlan).toHaveBeenLastCalledWith("u1", 3000, "2026-12-31");
  });

  it("says when the target is already met, or can't be priced", async () => {
    await show();
    await screen.findByText("$3,095.00");
    fetchPlan.mockResolvedValueOnce(planned({ goal: { ...goal, shortfall: -500, extra_hours_per_week: null,
      base_end_balance: 2500 } }));
    ask("2000");
    expect(await screen.findByText(/Already on track/)).toBeTruthy();

    fetchPlan.mockResolvedValueOnce(planned({ goal: null }));
    ask("2000");
    expect(await screen.findByText(/without an hourly job that has a rate/)).toBeTruthy();
  });

  it("shows why it couldn't answer", async () => {
    await show();
    await screen.findByText("$3,095.00");
    fetchPlan.mockRejectedValueOnce(new Error("The target date has to be after today"));
    ask("2000");
    expect((await screen.findByRole("alert")).textContent).toBe("The target date has to be after today");
  });

  it("says nothing with nothing held and nothing moving, or on a failed read", async () => {
    const empty = await show(planned({
      starting_balance: 0,
      months: [{ month: "2026-10-01", money_in: 0, money_out: 0, end_balance: 0 }],
    }));
    await Promise.resolve();
    expect(empty.container.innerHTML).toBe("");
    empty.unmount();

    const failed = await show(new Error("500"));
    await Promise.resolve();
    expect(failed.container.innerHTML).toBe("");
  });
});
