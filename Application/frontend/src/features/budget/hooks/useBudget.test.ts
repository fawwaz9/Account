// @vitest-environment jsdom
import { renderHook, waitFor, act } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * What a month step costs.
 *
 * Only `fetchBudgetSummary` takes the month. Everything else on this page is
 * the same figure whichever month is being looked at, so stepping the picker
 * used to refetch seven answers that could not have changed and re-send a
 * write on top of them. This counts the requests, because that is the only way
 * the saving is visible -- nothing on screen looks different either way.
 */
const calls = {
  runRecurring: vi.fn(async () => undefined),
  fetchAccounts: vi.fn(async () => []),
  fetchTransactions: vi.fn(async () => []),
  fetchCategories: vi.fn(async () => []),
  fetchBudgetSummary: vi.fn(async () => null),
  fetchRecurring: vi.fn(async () => []),
  fetchUpcoming: vi.fn(async () => []),
  fetchSafeToSpend: vi.fn(async () => null),
  fetchNetWorth: vi.fn(async () => null),
};

vi.mock("../api", () => calls);
vi.mock("../../../app/auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: "11111111-1111-1111-1111-111111111111" } }),
}));

const { useBudget } = await import("./useBudget");

/** Everything the page reads that is not the month's own summary. */
const MONTH_INDEPENDENT = [
  "fetchAccounts",
  "fetchTransactions",
  "fetchCategories",
  "fetchRecurring",
  "fetchUpcoming",
  "fetchSafeToSpend",
  "fetchNetWorth",
] as const;

beforeEach(() => {
  for (const fn of Object.values(calls)) fn.mockClear();
});

describe("useBudget", () => {
  it("loads everything once on mount, after catching up on standing payments", async () => {
    const { result } = renderHook(() => useBudget());
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(calls.runRecurring).toHaveBeenCalledTimes(1);
    expect(calls.fetchBudgetSummary).toHaveBeenCalledTimes(1);
    for (const name of MONTH_INDEPENDENT) {
      expect(calls[name], name).toHaveBeenCalledTimes(1);
    }
  });

  it("asks for one thing when the month changes, not eight", async () => {
    const { result } = renderHook(() => useBudget());
    await waitFor(() => expect(result.current.loading).toBe(false));
    for (const fn of Object.values(calls)) fn.mockClear();

    act(() => result.current.setMonth("2026-08-01"));
    await waitFor(() => expect(calls.fetchBudgetSummary).toHaveBeenCalledTimes(1));

    expect(calls.fetchBudgetSummary).toHaveBeenCalledWith(
      "11111111-1111-1111-1111-111111111111",
      "2026-08-01"
    );
    // The seven that cannot have changed, and the write that had nothing to do.
    for (const name of MONTH_INDEPENDENT) {
      expect(calls[name], name).not.toHaveBeenCalled();
    }
    expect(calls.runRecurring).not.toHaveBeenCalled();
  });

  it("does not blank the page while a new month loads", async () => {
    const { result } = renderHook(() => useBudget());
    await waitFor(() => expect(result.current.loading).toBe(false));

    // `loading` gates the whole page body, so a month step used to hide the
    // accounts, the ledger and the charts to fetch one figure.
    act(() => result.current.setMonth("2026-08-01"));
    expect(result.current.loading).toBe(false);
  });

  it("still reloads everything when money moves", async () => {
    const { result } = renderHook(() => useBudget());
    await waitFor(() => expect(result.current.loading).toBe(false));
    for (const fn of Object.values(calls)) fn.mockClear();

    // `reload` is what all 18 mutation sites call. Narrowing that is a separate
    // piece of work with real staleness risk, so it deliberately still catches
    // up and refetches the lot.
    await act(async () => {
      await result.current.reload();
    });

    expect(calls.runRecurring).toHaveBeenCalledTimes(1);
    expect(calls.fetchBudgetSummary).toHaveBeenCalledTimes(1);
    for (const name of MONTH_INDEPENDENT) {
      expect(calls[name], name).toHaveBeenCalledTimes(1);
    }
  });
});
