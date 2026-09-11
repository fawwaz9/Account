import { useCallback, useEffect, useRef, useState } from "react";
import { fetchAccounts, fetchBudgetSummary, fetchCategories, fetchTransactions } from "../api";
import { Account, BudgetSummary, SpendCategory, Transaction } from "../types";
import { currentMonth, daysAgo, localToday } from "../dates";
import { useAuth } from "../../../app/auth/AuthContext";

/** Accounts with their balances, and the recent ledger, loaded together. */
export function useBudget() {
  const { user } = useAuth();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [categories, setCategories] = useState<SpendCategory[]>([]);
  const [summary, setSummary] = useState<BudgetSummary | null>(null);
  const [month, setMonth] = useState(currentMonth());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Every load takes a ticket, and only the newest one is allowed to write state.
  // Stepping the month picker quickly fires several loads at once: without this,
  // September resolving after October leaves September's figures under October's
  // label, and the stale setLoading(false) clears the spinner so nothing on
  // screen signals the mismatch. A cleanup-scoped flag would not do, because
  // `load` is also handed out as `reload` and called outside any effect.
  const latestRequest = useRef(0);

  const load = useCallback(async () => {
    if (!user) {
      setLoading(false);
      return;
    }

    const ticket = ++latestRequest.current;

    setLoading(true);
    setError(null);

    try {
      // Balances derive from transactions, so the two must be read together or
      // the totals and the list can disagree on screen.
      const [nextAccounts, nextTransactions, nextCategories, nextSummary] = await Promise.all([
        fetchAccounts(user.id),
        // Only what is genuinely recent; the whole history lives on each
        // account's own page.
        fetchTransactions(user.id, { start: daysAgo(1), end: localToday() }),
        fetchCategories(user.id),
        fetchBudgetSummary(user.id, month),
      ]);
      if (ticket !== latestRequest.current) return;
      setAccounts(nextAccounts);
      setTransactions(nextTransactions);
      setCategories(nextCategories);
      setSummary(nextSummary);
    } catch (err) {
      if (ticket !== latestRequest.current) return;
      setError(err instanceof Error ? err.message : "Could not load your budget");
    } finally {
      // Only the newest load owns the spinner: a superseded one clearing it
      // would say "done" while the current request is still in flight.
      if (ticket === latestRequest.current) setLoading(false);
    }
  }, [user, month]);

  useEffect(() => {
    load();
  }, [load]);

  return {
    accounts,
    transactions,
    categories,
    summary,
    month,
    setMonth,
    loading,
    error,
    reload: load,
  };
}
