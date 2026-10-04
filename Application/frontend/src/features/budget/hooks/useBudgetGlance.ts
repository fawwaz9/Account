import { useEffect, useState } from "react";
import { fetchAccounts, fetchBudgetSummary, fetchNetWorth } from "../api";
import { Account, BudgetSummary, NetWorth } from "../types";
import { firstOfMonth, today } from "../../../shared/utils/dateUtils";
import { useAuth } from "../../../app/auth/AuthContext";

/**
 * Just what the dashboard shows: balances and this month's plan against spend.
 * Deliberately lighter than useBudget, which also pulls the whole ledger.
 */
export function useBudgetGlance() {
  const { user } = useAuth();
  // The id, not the object. `refreshUser()` builds a fresh `user` every time,
  // so depending on the object meant one Settings save re-ran every mounted
  // hook's entire fetch -- the id is what this actually needs, and it does not
  // change.
  const userId = user?.id;
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [summary, setSummary] = useState<BudgetSummary | null>(null);
  const [worth, setWorth] = useState<NetWorth | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!userId) return;

    let cancelled = false;
    Promise.all([
      fetchAccounts(userId),
      fetchBudgetSummary(userId, firstOfMonth(today())),
      fetchNetWorth(userId),
    ])
      .then(([nextAccounts, nextSummary, nextWorth]) => {
        if (cancelled) return;
        setAccounts(nextAccounts);
        setSummary(nextSummary);
        setWorth(nextWorth);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load your budget");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [userId]);

  // Was a client-side sum of every balance, which counted a credit card as
  // savings and money someone else was holding as money in your pocket. The
  // server owns the rule now, so this figure and the budget page's agree by
  // construction rather than by both being written the same way twice.
  const totalBalance = worth?.net_worth ?? 0;

  // Read successfully, as opposed to not yet answered or failed.
  const loaded = summary !== null && error === null;

  return { accounts, summary, totalBalance, netWorth: worth, error, loaded };
}
