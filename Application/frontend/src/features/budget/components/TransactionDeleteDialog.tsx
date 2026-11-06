import DeleteConfirmModal from "../../grades/components/DeleteConfirmModal";
import { useTransactionDelete } from "../hooks/useTransactionDelete";
import { formatMoney } from "../money";
import { Transaction } from "../types";
import { shortDate } from "../../../shared/utils/dateUtils";

/** What the confirmation says for one row, and whether it offers just this share. */
export interface DeleteWording {
  readonly title: string;
  readonly message: string;
  readonly confirmLabel: string;
  readonly offersShare: boolean;
}

/**
 * The confirmation for deleting a ledger row, worded for what will actually go.
 *
 * Every row asks first (audit H9): a mis-tap on the × used to change balances,
 * the month's spending and safe-to-spend with no way back. A paycheque's share
 * never offers "just this share" (audit H5): the cheque and its other shares
 * go together, and the server refuses one share alone.
 */
export function deleteWording(transaction: Transaction): DeleteWording {
  const what = `"${transaction.description || "This row"}", ${formatMoney(transaction.amount)} on ` +
    `${shortDate(transaction.occurred_on)}`;
  // Said because the student might expect it back: the standing payment marks
  // its day as dealt with, so the catch-up won't write it again (audit C1).
  const standing = transaction.recurring_id
    ? " It came from a standing payment, which won't write it again."
    : "";

  if (transaction.kind === "transfer") {
    return {
      title: "Delete this transfer?",
      message: `${what}. Both sides of the transfer are deleted.${standing}`,
      confirmLabel: "Delete transfer",
      offersShare: false,
    };
  }
  if (transaction.paycheque_id) {
    const shares = transaction.group_size > 1 ? ` and all ${transaction.group_size} of its shares` : "";
    return {
      title: "Delete this paycheque?",
      message: `${what} is part of a paycheque. Deleting it deletes the cheque from the Jobs page${shares}. ` +
        "To change how it was split, edit the cheque instead.",
      confirmLabel: "Delete the cheque",
      offersShare: false,
    };
  }
  if (transaction.group_size > 1) {
    return {
      title: "Remove which part?",
      message: `"${transaction.description || "This deposit"}" was split across ` +
        `${transaction.group_size} accounts. Remove only this account's share, or the whole deposit?${standing}`,
      confirmLabel: "Whole deposit",
      offersShare: true,
    };
  }
  return {
    title: "Delete this transaction?",
    message: `${what}. This can't be undone.${standing}`,
    confirmLabel: "Delete",
    offersShare: false,
  };
}

/** The delete confirmation for whichever row `remove` is holding; nothing while it holds none. */
export default function TransactionDeleteDialog({ remove }: {
  readonly remove: ReturnType<typeof useTransactionDelete>;
}) {
  const wording = remove.pending ? deleteWording(remove.pending) : null;

  return (
    <DeleteConfirmModal
      open={wording !== null}
      title={wording?.title ?? ""}
      message={wording?.message ?? ""}
      confirmLabel={wording?.confirmLabel}
      secondaryAction={wording?.offersShare ? { label: "Just this share", onConfirm: remove.deleteRow } : undefined}
      onConfirm={remove.deleteGroup}
      onCancel={remove.cancel}
      submitting={remove.deletingId !== null}
      error={remove.error}
    />
  );
}
