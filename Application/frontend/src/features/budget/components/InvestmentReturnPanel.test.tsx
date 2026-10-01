// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { InvestmentReturn } from "../types";

/**
 * The one place a reading gets typed, and the only reason any other figure in
 * this feature has anything to show.
 *
 * Two things here are worth more than the rest: that what reaches the server is
 * the market value **for the month on screen**, and that a figure carried forward
 * from an earlier month never pre-fills this month's field. The second is the
 * trap -- pre-filling it would mean saving without touching anything silently
 * re-records an old reading as current, which is the same class of fault as the
 * Settings timezone bug.
 */

// Typed with their real signatures so `mock.calls[0]` is a real tuple; without it
// the payload assertions need a cast that `tsc --noEmit` rejects, and the suite
// would pass while `npm run build` failed.
const setAccountMonthValue = vi.fn(
  async (_userId: string, _accountId: string, _month: string, _value: number) => ({}),
);
const clearAccountMonthValue = vi.fn(
  async (_userId: string, _accountId: string, _month: string) => ({}),
);
vi.mock("../api", () => ({ setAccountMonthValue, clearAccountMonthValue }));
vi.mock("../../../app/auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: "user-1" } }),
}));

const { default: InvestmentReturnPanel } = await import("./InvestmentReturnPanel");

function reading(over: Partial<InvestmentReturn> = {}): InvestmentReturn {
  return {
    difference_amount: 543.21,
    return_percent: 5.4,
    as_of: "2026-03-01",
    is_carried_forward: false,
    ledger_balance: 10_000,
    market_value: 10_543.21,
    month_gain: null,
    ...over,
  };
}

function show(over: Record<string, unknown> = {}) {
  return render(
    <InvestmentReturnPanel
      accountId="acct-tfsa"
      month="2026-03-01"
      figure={null}
      ledgerAtMonth={10_000}
      onSaved={vi.fn()}
      {...over}
    />,
  );
}

const field = () => screen.getByLabelText("What is it worth today?");
const saveButton = () =>
  screen.getByRole("button", { name: "Save" }) as HTMLButtonElement;

beforeEach(() => {
  setAccountMonthValue.mockClear();
  clearAccountMonthValue.mockClear();
});
afterEach(cleanup);

describe("recording a reading", () => {
  it("sends the typed market value against the month on screen", async () => {
    show({ month: "2026-03-01" });

    fireEvent.change(field(), { target: { value: "10543.21" } });
    fireEvent.click(saveButton());

    await waitFor(() => expect(setAccountMonthValue).toHaveBeenCalledTimes(1));
    expect(setAccountMonthValue.mock.calls[0]).toEqual([
      "user-1",
      "acct-tfsa",
      "2026-03-01",
      10543.21,
    ]);
  });

  it("records against the month shown, not against today", async () => {
    show({ month: "2026-01-01" });

    fireEvent.change(field(), { target: { value: "500" } });
    fireEvent.click(saveButton());

    await waitFor(() => expect(setAccountMonthValue).toHaveBeenCalled());
    expect(setAccountMonthValue.mock.calls[0][2]).toBe("2026-01-01");
  });

  it("cannot be saved empty", () => {
    show();

    expect(saveButton().disabled).toBe(true);
    fireEvent.click(saveButton());
    expect(setAccountMonthValue).not.toHaveBeenCalled();
  });

  it("reloads the page's figures after saving, not just its own", async () => {
    const onSaved = vi.fn();
    show({ onSaved });

    fireEvent.change(field(), { target: { value: "11000" } });
    fireEvent.click(saveButton());

    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
  });

  it("says so when the save fails instead of appearing to have worked", async () => {
    setAccountMonthValue.mockRejectedValueOnce(new Error("nope"));
    show();

    fireEvent.change(field(), { target: { value: "11000" } });
    fireEvent.click(saveButton());

    await waitFor(() => expect(screen.getByText(/did not save/i)).toBeTruthy());
  });
});

describe("the preview, before anything is saved", () => {
  it("shows what the typed figure makes the return", () => {
    show({ ledgerAtMonth: 10_000 });

    fireEvent.change(field(), { target: { value: "10543.21" } });

    expect(screen.getByText(/up \$543\.21/)).toBeTruthy();
    expect(screen.getByText(/\+5\.4%/)).toBeTruthy();
  });

  it("shows a holding worth less than the ledger as down, not up", () => {
    show({ ledgerAtMonth: 10_000 });

    fireEvent.change(field(), { target: { value: "9187.60" } });

    expect(screen.getByText(/down \$812\.40/)).toBeTruthy();
    expect(screen.getByText(/−8\.1%/)).toBeTruthy();
  });

  it("measures against the month's ledger, not the account's all-time balance", () => {
    // The whole reason the server sends a dated figure. With an all-time balance
    // of $15,000 this preview would read "down $4,500" for a real gain.
    show({ ledgerAtMonth: 10_000 });

    fireEvent.change(field(), { target: { value: "10500" } });

    expect(screen.getByText(/up \$500\.00/)).toBeTruthy();
  });

  it("offers no percentage when there is nothing to divide by", () => {
    // Zero paid in: the division has no answer, so only the dollar figure shows.
    show({ ledgerAtMonth: 0 });

    fireEvent.change(field(), { target: { value: "250" } });

    expect(screen.getByText(/up \$250\.00/)).toBeTruthy();
    expect(screen.queryByText(/%/)).toBeNull();
  });
});

describe("a figure carried forward from an earlier month", () => {
  it("does not pre-fill this month's field", () => {
    // The trap. Pre-filled, pressing Save without touching anything would record
    // March's reading as May's -- a save changing something nobody asked about.
    show({
      month: "2026-05-01",
      figure: reading({ is_carried_forward: true, as_of: "2026-03-01" }),
    });

    expect((field() as HTMLInputElement).value).toBe("");
    expect(saveButton().disabled).toBe(true);
  });

  it("says which month it came from", () => {
    show({
      month: "2026-05-01",
      figure: reading({ is_carried_forward: true, as_of: "2026-03-01" }),
    });

    expect(screen.getByText(/carried forward from March 2026/)).toBeTruthy();
  });

  it("offers no way to clear a month it is only borrowing a figure for", () => {
    // Clearing here would delete March's reading from a screen showing May.
    show({
      month: "2026-05-01",
      figure: reading({ is_carried_forward: true, as_of: "2026-03-01" }),
    });

    expect(screen.queryByRole("button", { name: /clear/i })).toBeNull();
  });
});

describe("a reading this month holds", () => {
  it("shows back the number that was typed", () => {
    show({ month: "2026-03-01", figure: reading() });

    expect((field() as HTMLInputElement).value).toBe("10543.21");
  });

  it("states the level and what it is measured against", () => {
    show({ month: "2026-03-01", figure: reading() });

    expect(screen.getByText("+$543.21")).toBeTruthy();
    expect(screen.getByText(/above the \$10,000\.00 you put in/)).toBeTruthy();
    expect(screen.getByText(/recorded for March 2026/)).toBeTruthy();
  });

  it("states a loss as below what you put in", () => {
    show({
      month: "2026-03-01",
      figure: reading({ difference_amount: -812.4, return_percent: -8.1 }),
    });

    expect(screen.getByText("−$812.40")).toBeTruthy();
    expect(screen.getByText(/below the/)).toBeTruthy();
  });
});

describe("clearing a month", () => {
  it("asks before destroying the reading", () => {
    show({ month: "2026-03-01", figure: reading() });

    fireEvent.click(screen.getByRole("button", { name: /clear this month/i }));

    expect(screen.getByText(/will be removed/)).toBeTruthy();
    expect(clearAccountMonthValue).not.toHaveBeenCalled();
  });

  it("clears only once confirmed", async () => {
    show({ month: "2026-03-01", figure: reading() });

    fireEvent.click(screen.getByRole("button", { name: /clear this month/i }));
    fireEvent.click(screen.getByRole("button", { name: "Clear it" }));

    await waitFor(() => expect(clearAccountMonthValue).toHaveBeenCalledTimes(1));
    expect(clearAccountMonthValue.mock.calls[0]).toEqual([
      "user-1",
      "acct-tfsa",
      "2026-03-01",
    ]);
  });

  it("does nothing if the confirmation is dismissed", () => {
    show({ month: "2026-03-01", figure: reading() });

    fireEvent.click(screen.getByRole("button", { name: /clear this month/i }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(clearAccountMonthValue).not.toHaveBeenCalled();
  });
});

describe("with nothing recorded at all", () => {
  it("invites a reading rather than showing an empty panel", () => {
    show({ figure: null });

    expect(screen.getByText(/Nothing recorded for this month/)).toBeTruthy();
    expect(field()).toBeTruthy();
  });

  it("explains what the figure means behind a question mark, not as muted text", () => {
    show({ figure: null });

    const tip = screen.getByRole("button", { name: "What this figure means" });
    expect(screen.queryByText(/sum of what you have paid in/)).toBeNull();

    fireEvent.click(tip);
    expect(screen.getByText(/sum of what you have paid in/)).toBeTruthy();
  });
});
