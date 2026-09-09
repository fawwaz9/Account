import { useCallback, useEffect, useState } from "react";
import { fetchAccounts, fetchBudgetSummary, fetchCategories, fetchTransactions } from "../api";
import { Account, BudgetSummary, SpendCategory, Transaction } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";

/** Accounts with their balances, and the recent ledger, loaded together. */
/** First of the current month, which is how a month is keyed throughout. */
function currentMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
}

export function useBudget() {
  const { user } = useAuth();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [categories, setCategories] = useState<SpendCategory[]>([]);
  const [summary, setSummary] = useState<BudgetSummary | null>(null);
  const [month, setMonth] = useState(currentMonth());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!user) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // Balances derive from transactions, so the two must be read together or
      // the totals and the list can disagree on screen.
      const [nextAccounts, nextTransactions, nextCategories, nextSummary] = await Promise.all([
        fetchAccounts(user.id),
        fetchTransactions(user.id),
        fetchCategories(user.id),
        fetchBudgetSummary(user.id, month),
      ]);
      setAccounts(nextAccounts);
      setTransactions(nextTransactions);
      setCategories(nextCategories);
      setSummary(nextSummary);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load your budget");
    } finally {
      setLoading(false);
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
