import { useCallback, useEffect, useRef, useState } from "react";
import { fetchAccountActivity, fetchCategories, fetchTransactions } from "../api";
import { AccountActivity, SpendCategory, Transaction } from "../types";
import { currentMonth } from "../dates";
import { useAuth } from "../../../app/auth/AuthContext";

/** One account's selected month: its figures, its ledger and the category list. */
export function useAccountActivity(accountId: string | undefined) {
  const [activity, setActivity] = useState<AccountActivity | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [categories, setCategories] = useState<SpendCategory[]>([]);
  const [month, setMonth] = useState(currentMonth());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { user } = useAuth();

  // Every load takes a ticket, and only the newest one is allowed to write state.
  // Stepping the month picker quickly fires several loads at once: without this,
  // September resolving after October leaves September's figures under October's
  // label, and the stale setLoading(false) clears the spinner so nothing on
  // screen signals the mismatch. A cleanup-scoped flag would not do, because
  // `load` is also handed out as `reload` and called outside any effect.
  const latestRequest = useRef(0);

  const load = useCallback(async () => {
    if (!user || !accountId) {
      setLoading(false);
      return;
    }

    const ticket = ++latestRequest.current;

    setLoading(true);
    setError(null);

    try {
      // The figures and the rows behind them are read together, for the same
      // reason the budget page reads balances and transactions together: two
      // round trips can straddle an edit and disagree on screen.
      const [nextActivity, nextTransactions, nextCategories] = await Promise.all([
        fetchAccountActivity(user.id, accountId, month),
        fetchTransactions(user.id, {
          accountId,
          start: month,
          end: lastOfMonth(month),
        }),
        fetchCategories(user.id),
      ]);
      if (ticket !== latestRequest.current) return;
      setActivity(nextActivity);
      setTransactions(nextTransactions);
      setCategories(nextCategories);
    } catch (err) {
      if (ticket !== latestRequest.current) return;
      setError(err instanceof Error ? err.message : "Could not load that account");
    } finally {
      // Only the newest load owns the spinner: a superseded one clearing it
      // would say "done" while the current request is still in flight.
      if (ticket === latestRequest.current) setLoading(false);
    }
  }, [user, accountId, month]);

  useEffect(() => {
    load();
  }, [load]);

  return { activity, transactions, categories, month, setMonth, loading, error, reload: load };
}

/** Last day of the month a YYYY-MM-01 string names. */
function lastOfMonth(month: string): string {
  const [year, index] = month.split("-").map(Number);
  // Day 0 of the next month is the last day of this one, and the Date
  // constructor rolls December over to January on its own.
  const last = new Date(year, index, 0);
  return `${last.getFullYear()}-${String(last.getMonth() + 1).padStart(2, "0")}-${String(
    last.getDate()
  ).padStart(2, "0")}`;
}
