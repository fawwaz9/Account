import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchAccounts,
  fetchBudgetSummary,
  fetchCategories,
  fetchRecurring,
  fetchTransactions,
  fetchUpcoming,
  runRecurring,
} from "../api";
import {
  Account,
  BudgetSummary,
  RecurringTransaction,
  SpendCategory,
  Transaction,
  UpcomingCharge,
} from "../types";
import { currentMonth, daysAgo, daysAhead, localToday } from "../dates";
import { useAuth } from "../../../app/auth/AuthContext";

/** Accounts with their balances, and the recent ledger, loaded together. */
export function useBudget() {
  const { user } = useAuth();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [categories, setCategories] = useState<SpendCategory[]>([]);
  const [summary, setSummary] = useState<BudgetSummary | null>(null);
  const [recurring, setRecurring] = useState<RecurringTransaction[]>([]);
  const [upcoming, setUpcoming] = useState<UpcomingCharge[]>([]);
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
      // Any standing payment that has come due is written before anything is
      // read, or the balances below would be a month out of date until the
      // student happened to open some other screen. Idempotent -- a payment is
      // keyed by (rule, date) -- so doing this on every load charges nothing
      // twice. Failures are swallowed deliberately: not being able to catch up
      // must not stop the budget from rendering at all.
      await runRecurring(user.id).catch(() => undefined);
      if (ticket !== latestRequest.current) return;

      // Balances derive from transactions, so the two must be read together or
      // the totals and the list can disagree on screen.
      const [
        nextAccounts,
        nextTransactions,
        nextCategories,
        nextSummary,
        nextRecurring,
        nextUpcoming,
      ] = await Promise.all([
        fetchAccounts(user.id),
        // Only what is genuinely recent; the whole history lives on each
        // account's own page.
        fetchTransactions(user.id, { start: daysAgo(1), end: localToday() }),
        fetchCategories(user.id),
        fetchBudgetSummary(user.id, month),
        fetchRecurring(user.id),
        // Six weeks ahead: far enough to see the next rent and the next
        // subscription, near enough that it is still what you are committed to
        // rather than a forecast.
        fetchUpcoming(user.id, localToday(), daysAhead(42)),
      ]);
      if (ticket !== latestRequest.current) return;
      setAccounts(nextAccounts);
      setTransactions(nextTransactions);
      setCategories(nextCategories);
      setSummary(nextSummary);
      setRecurring(nextRecurring);
      setUpcoming(nextUpcoming);
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
    recurring,
    upcoming,
    summary,
    month,
    setMonth,
    loading,
    error,
    reload: load,
  };
}
