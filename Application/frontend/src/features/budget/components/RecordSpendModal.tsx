import { useEffect, useState } from "react";
import { createTransaction } from "../api";
import { SpendCategory } from "../types";
import { Course } from "../../grades/types";
import CoursePicker from "./CoursePicker";
import { getErrorMessage } from "../../grades/components/AddCourseModal";
import { useAuth } from "../../../app/auth/AuthContext";
import { today } from "../../../shared/utils/dateUtils";
import Modal from "../../../shared/components/Modal";

/** Props for recording spending from one account. */
interface RecordSpendModalProps {
  readonly open: boolean;
  /** The account on screen; the dialog never offers another. */
  readonly accountId: string;
  readonly accountName: string;
  readonly categories: readonly SpendCategory[];
  readonly courses: readonly Course[];
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

/**
 * Record an expense from the account on screen, with no account picker by design.
 * Stays open, holding the entry, when saving fails.
 */
export default function RecordSpendModal({
  open,
  accountId,
  accountName,
  categories,
  courses,
  onClose,
  onSaved,
}: RecordSpendModalProps) {
  const { user } = useAuth();
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [occurredOn, setOccurredOn] = useState(today());
  const [categoryId, setCategoryId] = useState("");
  const [courseId, setCourseId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Cleared on open, so a previous entry never carries into a new one.
  //
  // Depends on `open` alone, deliberately -- the same trap AddMoneyModal
  // documents. Depending on `categories` as well would wipe a half-typed entry
  // whenever a background reload rebuilt that array, with nothing on screen to
  // explain where it went.
  useEffect(() => {
    if (!open) return;
    setAmount("");
    setDescription("");
    setOccurredOn(today());
    setCategoryId("");
    setCourseId("");
    setError(null);
  }, [open]);

  if (!open) return null;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;

    setSubmitting(true);
    setError(null);
    try {
      await createTransaction(user.id, {
        kind: "expense",
        // The account on screen, never a selection. Nothing in this dialog can
        // change it.
        account_id: accountId,
        amount: Number(amount),
        description: description.trim() || null,
        occurred_on: occurredOn,
        category_id: categoryId || null,
        course_id: courseId || null,
      });
      onSaved();
      onClose();
    } catch (err) {
      // Left open on failure, holding what was typed. Closing here would throw
      // the entry away at the exact moment it could not be saved.
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal title={`Record spending — ${accountName}`} onClose={onClose}>
      <form className="loginForm" onSubmit={handleSubmit}>
        <div className="loginField">
          <label htmlFor="spend-amount">Amount</label>
          <input
            id="spend-amount"
            className="loginInput"
            type="number"
            min={0.01}
            step="0.01"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            required
          />
        </div>

        {categories.length > 0 && (
          <div className="loginField">
            <label htmlFor="spend-category">Category</label>
            <select
              id="spend-category"
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
          <label htmlFor="spend-description">Description</label>
          <input
            id="spend-description"
            className="loginInput"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="e.g. Groceries"
          />
        </div>

        {/* Reads a course code out of the description, so a textbook files
            itself against the right course. Optional, and below the description
            because that is what it watches. */}
        {user && (
          <CoursePicker
            userId={user.id}
            courses={courses}
            value={courseId}
            onChange={setCourseId}
            description={description}
            idPrefix="spend"
          />
        )}

        <div className="loginField">
          <label htmlFor="spend-date">Date</label>
          <input
            id="spend-date"
            className="loginInput"
            type="date"
            value={occurredOn}
            onChange={(event) => setOccurredOn(event.target.value)}
            required
          />
        </div>

        {error && <p className="loginError">{error}</p>}

        <div className="flex justify-end gap-3 pt-2">
          <button type="button" className="buttons" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="loginSubmit" disabled={submitting}>
            {submitting ? "Recording..." : "Record"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
