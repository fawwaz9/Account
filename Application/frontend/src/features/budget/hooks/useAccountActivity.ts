import { useCallback, useEffect, useRef, useState } from "react";
import { fetchAccountActivity, fetchCategories, fetchTransactions } from "../api";
import { AccountActivity, SpendCategory, Transaction } from "../types";
import { firstOfMonth, today } from "../../../shared/utils/dateUtils";
import { useAuth } from "../../../app/auth/AuthContext";
import { useApiRefresh } from "../../../shared/hooks/useApiRefresh";

/**
 * One account's chosen month: its figures, its transactions and the category list.
 * Only the newest load may write state, so a quick month change never shows stale figures.
 */
export function useAccountActivity(accountId: string | undefined) {
  const [activity, setActivity] = useState<AccountActivity | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [categories, setCategories] = useState<SpendCategory[]>([]);
  const [month, setMonth] = useState(firstOfMonth(today()));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { user } = useAuth();
  // The id, not the object. `refreshUser()` builds a fresh `user` every time,
  // so depending on the object meant one Settings save re-ran every mounted
  // hook's entire fetch -- the id is what this actually needs, and it does not
  // change.
  const userId = user?.id;

  // Every load takes a ticket, and only the newest one is allowed to write state.
  // Stepping the month picker quickly fires several loads at once: without this,
  // September resolving after October leaves September's figures under October's
  // label, and the stale setLoading(false) clears the spinner so nothing on
  // screen signals the mismatch. A cleanup-scoped flag would not do, because
  // `load` is also handed out as `reload` and called outside any effect.
  const latestRequest = useRef(0);

  const load = useCallback(async () => {
    if (!userId || !accountId) {
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
        fetchAccountActivity(userId, accountId, month),
        fetchTransactions(userId, {
          accountId,
          start: month,
          end: lastOfMonth(month),
        }),
        fetchCategories(userId),
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
  }, [userId, accountId, month]);

  // Catch up when a background refetch finds something new (audit #35).
  useApiRefresh(load);

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
