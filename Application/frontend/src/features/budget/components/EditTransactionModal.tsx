import { useEffect, useState } from "react";
import { updateTransaction } from "../api";
import { SpendCategory, Transaction } from "../types";
import { getErrorMessage } from "../../grades/components/AddCourseModal";
import { useAuth } from "../../../app/auth/AuthContext";

interface EditTransactionModalProps {
  readonly transaction: Transaction | null;
  readonly categories: readonly SpendCategory[];
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

export default function EditTransactionModal({
  transaction,
  categories,
  onClose,
  onSaved,
}: EditTransactionModalProps) {
  const { user } = useAuth();
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [occurredOn, setOccurredOn] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reload the fields whenever a different row is opened, so one row's values
  // never linger into the next.
  useEffect(() => {
    if (!transaction) return;
    setAmount(String(transaction.amount));
    setDescription(transaction.description ?? "");
    setOccurredOn(transaction.occurred_on);
    setCategoryId(transaction.category_id ?? "");
    setError(null);
  }, [transaction]);

  if (!transaction) return null;

  const isTransfer = transaction.kind === "transfer";
  const isExpense = transaction.kind === "expense";

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user || !transaction) return;

    setSubmitting(true);
    setError(null);
    try {
      await updateTransaction(user.id, transaction.id, {
        amount: Number(amount),
        description: description || null,
        occurred_on: occurredOn,
        // Only expenses carry a category, so don't send one for anything else.
        ...(isExpense ? { category_id: categoryId || null } : {}),
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="popup">
      <div className="addCoursePopup">
        <h2>Edit {transaction.kind}</h2>

        {isTransfer && (
          <p className="muted small-text">
            Both sides of this transfer move together.
          </p>
        )}

        <form className="loginForm" onSubmit={handleSubmit}>
          <div className="loginField">
            <label htmlFor="edit-amount">Amount</label>
            <input
              id="edit-amount"
              className="loginInput"
              type="number"
              min={0.01}
              step="0.01"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              required
            />
          </div>

          <div className="loginField">
            <label htmlFor="edit-description">Description</label>
            <input
              id="edit-description"
              className="loginInput"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>

          {isExpense && categories.length > 0 && (
            <div className="loginField">
              <label htmlFor="edit-category">Category</label>
              <select
                id="edit-category"
                className="loginInput"
                value={categoryId}
                onChange={(event) => setCategoryId(event.target.value)}
              >
                <option value="">Uncategorised</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>{category.name}</option>
                ))}
              </select>
            </div>
          )}

          <div className="loginField">
            <label htmlFor="edit-date">Date</label>
            <input
              id="edit-date"
              className="loginInput"
              type="date"
              value={occurredOn}
              onChange={(event) => setOccurredOn(event.target.value)}
              required
            />
          </div>

          {error && <p className="loginError">{error}</p>}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700 !bg-slate-900 !text-slate-200"
              disabled={submitting}
            >
              Cancel
            </button>
            <button type="submit" className="loginSubmit" disabled={submitting}>
              {submitting ? "Saving..." : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
