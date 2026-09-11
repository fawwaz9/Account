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
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [summary, setSummary] = useState<BudgetSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;

    let cancelled = false;
    Promise.all([fetchAccounts(user.id), fetchBudgetSummary(user.id, currentMonth())])
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
  }, [user]);

  const totalBalance = accounts.reduce((sum, account) => sum + account.balance, 0);

  return { accounts, summary, totalBalance, error };
}
