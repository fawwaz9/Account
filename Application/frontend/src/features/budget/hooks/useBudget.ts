import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchNetWorth,
  fetchSafeToSpend,
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
  SafeToSpend,
  RecurringTransaction,
  SpendCategory,
  Transaction,
  UpcomingCharge,
  NetWorth,
} from "../types";
import { addDays, firstOfMonth, today } from "../../../shared/utils/dateUtils";
import { useAuth } from "../../../app/auth/AuthContext";
import { useApiRefresh } from "../../../shared/hooks/useApiRefresh";

/** Accounts with their balances, and the recent ledger, loaded together. */
export function useBudget() {
  const { user } = useAuth();
  // The id, not the object. `refreshUser()` builds a fresh `user` every time,
  // so depending on the object meant one Settings save re-ran every mounted
  // hook's entire fetch -- the id is what this actually needs, and it does not
  // change.
  const userId = user?.id;
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [categories, setCategories] = useState<SpendCategory[]>([]);
  const [summary, setSummary] = useState<BudgetSummary | null>(null);
  const [recurring, setRecurring] = useState<RecurringTransaction[]>([]);
  const [upcoming, setUpcoming] = useState<UpcomingCharge[]>([]);
  const [safe, setSafe] = useState<SafeToSpend | null>(null);
  const [worth, setWorth] = useState<NetWorth | null>(null);
  const [month, setMonth] = useState(firstOfMonth(today()));
  const [loading, setLoading] = useState(true);
  // Separate from `loading`, which gates the whole page body. A month step
  // changes two panels, so it says so on those two rather than emptying the
  // screen -- but it does have to say it somewhere, or the click looks like it
  // did nothing at all.
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Every load takes a ticket, and only the newest one is allowed to write state.
  // Stepping the month picker quickly fires several loads at once: without this,
  // September resolving after October leaves September's figures under October's
  // label, and the stale setLoading(false) clears the spinner so nothing on
  // screen signals the mismatch. A cleanup-scoped flag would not do, because
  // `load` is also handed out as `reload` and called outside any effect.
  //
  // Two tickets, because there are now two loads: a summary arriving late must
  // not be discarded because the accounts were refetched after it, and the
  // other way round.
  const latestRest = useRef(0);
  const latestSummary = useRef(0);

  /**
   * The month's own figure, and nothing else.
   *
   * Split out because it is the only one of the eight reads that takes `month`
   * at all. Everything below is the same whichever month is being looked at --
   * two of them are windowed on `today()` and the rest take no date -- so
   * stepping the picker used to refetch seven answers that could not have
   * changed, and re-send a write on top of them.
   *
   * It deliberately does not touch `loading`, which gates the whole page body:
   * blanking the accounts, the ledger and the charts to fetch one figure made a
   * month step look like a page load.
   */
  const loadSummary = useCallback(async () => {
    if (!userId) return;

    const ticket = ++latestSummary.current;
    setSummaryLoading(true);
    try {
      const next = await fetchBudgetSummary(userId, month);
      if (ticket !== latestSummary.current) return;
      setSummary(next);
    } catch (err) {
      if (ticket !== latestSummary.current) return;
      setError(err instanceof Error ? err.message : "Could not load your budget");
    } finally {
      if (ticket === latestSummary.current) setSummaryLoading(false);
    }
  }, [userId, month]);

  /** Everything that does not move with the month picker. */
  const loadRest = useCallback(async () => {
    if (!userId) {
      setLoading(false);
      return;
    }

    const ticket = ++latestRest.current;
    setLoading(true);
    setError(null);

    try {
      // Balances derive from transactions, so the two must be read together or
      // the totals and the list can disagree on screen.
      const [
        nextAccounts,
        nextTransactions,
        nextCategories,
        nextRecurring,
        nextUpcoming,
        nextSafe,
        nextWorth,
      ] = await Promise.all([
        fetchAccounts(userId),
        // Only what is genuinely recent; the whole history lives on each
        // account's own page.
        fetchTransactions(userId, { start: addDays(today(), -1), end: today() }),
        fetchCategories(userId),
        fetchRecurring(userId),
        // Six weeks ahead: far enough to see the next rent and the next
        // subscription, near enough that it is still what you are committed to
        // rather than a forecast.
        fetchUpcoming(userId, today(), addDays(today(), 42)),
        fetchSafeToSpend(userId),
        // All-time, so it does not move with the month picker above it.
        fetchNetWorth(userId),
      ]);
      if (ticket !== latestRest.current) return;
      setAccounts(nextAccounts);
      setTransactions(nextTransactions);
      setCategories(nextCategories);
      setRecurring(nextRecurring);
      setUpcoming(nextUpcoming);
      setSafe(nextSafe);
      setWorth(nextWorth);
    } catch (err) {
      if (ticket !== latestRest.current) return;
      setError(err instanceof Error ? err.message : "Could not load your budget");
    } finally {
      // Only the newest load owns the spinner: a superseded one clearing it
      // would say "done" while the current request is still in flight.
      if (ticket === latestRest.current) setLoading(false);
    }
  }, [userId]);

  /**
   * Catch up on standing payments, then read.
   *
   * The order is the point and is why this is one function rather than two
   * effects. Any payment that has come due is written before anything is read,
   * or the balances would be a month out of date until the student happened to
   * open some other screen -- and safe-to-spend in particular has to see a
   * payment written on this load as committed rather than as cash still in
   * hand. Idempotent, since a payment is keyed by (rule, date), so doing it
   * again charges nothing twice. Failures are swallowed deliberately: not being
   * able to catch up must not stop the budget rendering at all.
   */
  const load = useCallback(async () => {
    if (!userId) {
      setLoading(false);
      return;
    }

    await runRecurring(userId).catch(() => undefined);
    await Promise.all([loadRest(), loadSummary()]);
  }, [userId, loadRest, loadSummary]);

  // Which month the summary currently holds, and which user has had its first
  // load. Both are refs rather than state because nothing renders from them --
  // they only decide whether an effect has work to do.
  // Catch up when a background refetch finds something new (audit #35).
  useApiRefresh(load);

  const loadedMonth = useRef<string | null>(null);
  const loadedFor = useRef<string | null>(null);

  useEffect(() => {
    if (!userId) {
      setLoading(false);
      return;
    }

    // Once per user. `load` changes identity whenever the month does, so this
    // effect re-runs on a month step -- and returning here is the whole point
    // of the change: the effect below answers that with one request instead of
    // catching up and refetching all eight.
    if (loadedFor.current === userId) return;

    loadedFor.current = userId;
    loadedMonth.current = month;
    load();
  }, [userId, month, load]);

  useEffect(() => {
    // Nothing has loaded yet, or this month is already on screen: the effect
    // above owns the first fetch, and running here too would double it.
    if (loadedMonth.current === null || loadedMonth.current === month) return;

    loadedMonth.current = month;
    loadSummary();
  }, [month, loadSummary]);

  return {
    safe,
    worth,
    accounts,
    transactions,
    categories,
    recurring,
    upcoming,
    summary,
    month,
    setMonth,
    loading,
    summaryLoading,
    error,
    reload: load,
  };
}
