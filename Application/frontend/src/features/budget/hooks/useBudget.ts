import { useCallback, useEffect, useState } from "react";
import { fetchAccounts, fetchTransactions } from "../api";
import { Account, Transaction } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";

/** Accounts with their balances, and the recent ledger, loaded together. */
export function useBudget() {
  const { user } = useAuth();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
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
      const [nextAccounts, nextTransactions] = await Promise.all([
        fetchAccounts(user.id),
        fetchTransactions(user.id),
      ]);
      setAccounts(nextAccounts);
      setTransactions(nextTransactions);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load your budget");
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    load();
  }, [load]);

  return { accounts, transactions, loading, error, reload: load };
}
