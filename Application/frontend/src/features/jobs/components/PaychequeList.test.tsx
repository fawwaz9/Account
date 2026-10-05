// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

const checkPaycheque = vi.fn();
vi.mock("../api", () => ({ checkPaycheque: (...a: unknown[]) => checkPaycheque(...a) }));
vi.mock("../../../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));

import PaychequeList from "./PaychequeList";
import { PayCheck, Paycheque } from "../types";

const cheque: Paycheque = {
  id: "p1", job_id: "j1", job_name: "Bookstore", occurred_on: "2026-09-24",
  gross_amount: 444, deductions: [], net_amount: 444, period_start: "2026-09-06",
  period_end: "2026-09-19", expected_gross: 453.25, variance: -9.25, notes: null,
} as Paycheque;

const short: PayCheck = {
  paycheque_id: "p1", status: "short", summary: "Looks $9.25 short of what the hours come to.",
  actual_gross: 444, expected: 453.25, expected_with_vacation: 471.38, vacation_percent: 4,
  difference: -9.25,
  lines: [
    { label: "Regular hours", hours: 23, rate: 18.5, amount: 425.5, rule: null },
    { label: "Overtime, past 8 hours in a day", hours: 1, rate: 27.75, amount: 27.75,
      rule: "BC Employment Standards Act s.40(1): 1.5x for hours over 8 in a day" },
  ],
  notes: ["Statutory holiday pay isn't checked."],
};

function show(list: Paycheque[] = [cheque]) {
  return render(<PaychequeList paycheques={list} onEdit={vi.fn()} onAdd={vi.fn()} busy={false} />);
}

const button = () => screen.getByRole("button", { name: /Check the math on the cheque/ });

beforeEach(() => {
  checkPaycheque.mockReset();
});
afterEach(cleanup);

describe("PaychequeList's check", () => {
  it("shows the verdict, each line and its rule, when asked", async () => {
    checkPaycheque.mockResolvedValue(short);
    show();
    expect(screen.queryByRole("region", { name: "Cheque check" })).toBeNull();
    fireEvent.click(button());
    expect(await screen.findByText("Looks $9.25 short of what the hours come to.")).toBeTruthy();
    expect(checkPaycheque).toHaveBeenCalledWith("u1", "p1");
    expect(screen.getByText(/s\.40\(1\)/)).toBeTruthy();
    expect(screen.getByText("1 h × $27.75")).toBeTruthy();
    expect(screen.getByText("Statutory holiday pay isn't checked.")).toBeTruthy();
    expect(button().textContent).toBe("Hide the math");
  });

  it("acknowledges the press while it checks", async () => {
    let finish: (value: PayCheck) => void = () => {};
    checkPaycheque.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    show();
    fireEvent.click(button());
    expect(button().textContent).toBe("Checking…");
    expect((button() as HTMLButtonElement).disabled).toBe(true);
    finish(short);
    expect(await screen.findByText(/Looks \$9\.25 short/)).toBeTruthy();
  });

  it("hides on a second press, and reopens without asking again", async () => {
    checkPaycheque.mockResolvedValue(short);
    show();
    fireEvent.click(button());
    await screen.findByText(/Looks \$9\.25 short/);
    fireEvent.click(button());
    expect(screen.queryByText(/Looks \$9\.25 short/)).toBeNull();
    fireEvent.click(button());
    expect(await screen.findByText(/Looks \$9\.25 short/)).toBeTruthy();
    expect(checkPaycheque).toHaveBeenCalledTimes(1);
  });

  it("asks again once the list changes, since the cheque may have", async () => {
    checkPaycheque.mockResolvedValue(short);
    const { rerender } = show();
    fireEvent.click(button());
    await screen.findByText(/Looks \$9\.25 short/);
    fireEvent.click(button()); // hide
    rerender(<PaychequeList paycheques={[{ ...cheque }]} onEdit={vi.fn()} onAdd={vi.fn()} busy={false} />);
    fireEvent.click(button());
    await screen.findByText(/Looks \$9\.25 short/);
    expect(checkPaycheque).toHaveBeenCalledTimes(2);
  });

  it("says so when the check fails", async () => {
    checkPaycheque.mockRejectedValue(new Error("500"));
    show();
    fireEvent.click(button());
    expect((await screen.findByRole("alert")).textContent).toContain("Couldn't check this cheque");
  });
});
