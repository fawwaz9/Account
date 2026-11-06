import { useState } from "react";
import { deleteTransaction } from "../api";
import { Transaction } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";

/**
 * Transaction delete flow: every row asks first (audit H9), and a split deposit asks
 * which part. Returns the pending row and the dialog's handlers; reloads after each delete.
 */
export function useTransactionDelete(reload: () => Promise<void>) {
  const { user } = useAuth();
  const [pending, setPending] = useState<Transaction | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(transaction: Transaction, scope: "row" | "group") {
    if (!user) return;

    setDeletingId(transaction.id);
    setError(null);
    try {
      await deleteTransaction(user.id, transaction.id, scope);
      // Balances are derived from the rows, so the accounts have to be re-read.
      await reload();
      setPending(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete that");
    } finally {
      setDeletingId(null);
    }
  }

  // Held for the confirmation, never deleted straight away: a mis-tap on the ×
  // used to change balances with no way back. TransactionDeleteDialog words it.
  function requestDelete(transaction: Transaction) {
    setError(null);
    setPending(transaction);
  }

  return {
    requestDelete,
    deletingId,
    error,
    pending,
    cancel: () => setPending(null),
    deleteRow: () => pending && run(pending, "row"),
    deleteGroup: () => pending && run(pending, "group"),
  };
}
