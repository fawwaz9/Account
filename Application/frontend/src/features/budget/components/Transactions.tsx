import { Account, Transaction } from "../types";
import { formatMoney } from "../money";

interface TransactionsProps {
  readonly transactions: readonly Transaction[];
  readonly accounts: readonly Account[];
  readonly onDelete: (transaction: Transaction) => void;
  readonly onEdit: (transaction: Transaction) => void;
  readonly deletingId: string | null;
}

export default function Transactions({
  transactions,
  accounts,
  onDelete,
  onEdit,
  deletingId,
}: TransactionsProps) {
  const nameFor = (accountId: string) =>
    accounts.find((account) => account.id === accountId)?.name ?? "Unknown account";

  if (transactions.length === 0) {
    return <p className="muted small-text">No movements recorded yet.</p>;
  }

  return (
    <ul className="ledger">
      {transactions.map((transaction) => (
        <li className="ledgerRow" key={transaction.id}>
          <button
            type="button"
            className="ledgerOpen"
            onClick={() => onEdit(transaction)}
            aria-label={`Edit ${transaction.description || transaction.kind}`}
          >
            <span className={`ledgerKind ledgerKind--${transaction.kind}`}>
              {transaction.kind}
            </span>

            <span className="ledgerBody">
              <span className="ledgerDescription">
                {transaction.description || "(no description)"}
              </span>
              <span className="small-text muted">
                {transaction.occurred_on} &middot; {nameFor(transaction.account_id)}
              </span>
            </span>

            <span
              className={
                transaction.signed_amount < 0 ? "ledgerAmount ledgerOut" : "ledgerAmount ledgerIn"
              }
            >
              {formatMoney(transaction.signed_amount, { signed: true })}
            </span>
          </button>

          <button
            type="button"
            className="ledgerRemove"
            onClick={() => onDelete(transaction)}
            disabled={deletingId === transaction.id}
            aria-label={`Delete ${transaction.description || "transaction"}`}
            title={
              transaction.group_id
                ? "Deleting a transfer removes both sides"
                : "Delete this transaction"
            }
          >
            ×
          </button>
        </li>
      ))}
    </ul>
  );
}
