import { Account, Transaction } from "../types";
import { formatMoney } from "../money";

interface TransactionsProps {
  readonly transactions: readonly Transaction[];
  /** Only the id and name are read, so a single-account page can pass one entry. */
  readonly accounts: readonly Pick<Account, "id" | "name">[];
  readonly onDelete: (transaction: Transaction) => void;
  readonly onEdit: (transaction: Transaction) => void;
  readonly deletingId: string | null;
  /** Shown instead of the list when there is nothing in range. */
  readonly emptyMessage?: string;
}

/**
 * Newest day first, then alphabetically within a day.
 *
 * Rows with no description sort to the bottom of their day rather than to the
 * top: an empty string would otherwise win every comparison and push the
 * unlabelled rows above everything you can actually read.
 */
function byDayThenName(a: Transaction, b: Transaction) {
  if (a.occurred_on !== b.occurred_on) {
    return a.occurred_on < b.occurred_on ? 1 : -1;
  }

  const aName = a.description?.trim() ?? "";
  const bName = b.description?.trim() ?? "";
  if (!aName || !bName) {
    return Number(Boolean(bName)) - Number(Boolean(aName));
  }

  return aName.localeCompare(bName);
}

/** What the delete button will actually do, which depends on what kind of
    group the row belongs to -- not merely on whether it has one. */
function deleteHint(transaction: Transaction) {
  if (transaction.kind === "transfer") return "Deleting a transfer removes both sides";
  if (transaction.group_size > 1) return "Part of a split deposit -- you will be asked how much to remove";
  return "Delete this transaction";
}

export default function Transactions({
  transactions,
  accounts,
  onDelete,
  onEdit,
  deletingId,
  emptyMessage = "No movements recorded yet.",
}: TransactionsProps) {
  const nameFor = (accountId: string) =>
    accounts.find((account) => account.id === accountId)?.name ?? "Unknown account";

  if (transactions.length === 0) {
    return <p className="muted small-text">{emptyMessage}</p>;
  }

  const ordered = [...transactions].sort(byDayThenName);

  return (
    <ul className="ledger">
      {ordered.map((transaction) => (
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
            title={deleteHint(transaction)}
          >
            ×
          </button>
        </li>
      ))}
    </ul>
  );
}
