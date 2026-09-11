import { useState } from "react";
import { deleteTransaction } from "../api";
import { Transaction } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";

/**
 * Deleting a movement, including the question a split deposit has to ask.
 *
 * A transfer always goes whole -- half a transfer is not a thing -- and an
 * ungrouped row has nothing to ask about, so both delete immediately. Only a
 * deposit with siblings offers the choice between one allocation and all of it.
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

  function requestDelete(transaction: Transaction) {
    if (transaction.kind !== "transfer" && transaction.group_size > 1) {
      setPending(transaction);
      return;
    }

    void run(transaction, "group");
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
