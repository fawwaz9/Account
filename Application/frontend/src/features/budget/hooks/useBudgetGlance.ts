import { useEffect, useState } from "react";
import { fetchAccounts, fetchBudgetSummary } from "../api";
import { Account, BudgetSummary } from "../types";
import { currentMonth } from "../dates";
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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!userId) return;

    let cancelled = false;
    Promise.all([fetchAccounts(userId), fetchBudgetSummary(userId, currentMonth())])
      .then(([nextAccounts, nextSummary]) => {
        if (cancelled) return;
        setAccounts(nextAccounts);
        setSummary(nextSummary);
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

  const totalBalance = accounts.reduce((sum, account) => sum + account.balance, 0);

  return { accounts, summary, totalBalance, error };
}
