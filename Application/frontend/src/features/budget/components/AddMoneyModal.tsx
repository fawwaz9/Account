import { useEffect, useState } from "react";
import { createTransaction, createTransfer } from "../api";
import { Account } from "../types";
import { getErrorMessage } from "../../grades/components/AddCourseModal";
import { useAuth } from "../../../app/auth/AuthContext";

interface AddMoneyModalProps {
  readonly open: boolean;
  readonly accounts: readonly Account[];
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

type Mode = "income" | "expense" | "transfer";

const today = () => new Date().toISOString().slice(0, 10);

export default function AddMoneyModal({
  open,
  accounts,
  onClose,
  onSaved,
}: AddMoneyModalProps) {
  const { user } = useAuth();
  const [mode, setMode] = useState<Mode>("expense");
  const [accountId, setAccountId] = useState("");
  const [toAccountId, setToAccountId] = useState("");
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [occurredOn, setOccurredOn] = useState(today());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Default the pickers once accounts arrive, and reset on each open so a
  // previous entry never carries over into a new one.
  useEffect(() => {
    if (!open || accounts.length === 0) return;
    setAccountId(accounts[0].id);
    setToAccountId(accounts[1]?.id ?? accounts[0].id);
    setAmount("");
    setDescription("");
    setOccurredOn(today());
    setError(null);
  }, [open, accounts]);

  if (!open) return null;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;

    setSubmitting(true);
    setError(null);

    try {
      if (mode === "transfer") {
        await createTransfer(user.id, {
          from_account_id: accountId,
          to_account_id: toAccountId,
          amount: Number(amount),
          description: description || null,
          occurred_on: occurredOn,
        });
      } else {
        await createTransaction(user.id, {
          kind: mode,
          account_id: accountId,
          amount: Number(amount),
          description: description || null,
          occurred_on: occurredOn,
        });
      }
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
        <h2>Record Money</h2>

        <div className="moneyTabs">
          {(["expense", "income", "transfer"] as Mode[]).map((option) => (
            <button
              type="button"
              key={option}
              className={mode === option ? "moneyTab moneyTabActive" : "moneyTab"}
              onClick={() => {
                setMode(option);
                setError(null);
              }}
            >
              {option}
            </button>
          ))}
        </div>

        <form className="loginForm" onSubmit={handleSubmit}>
          <div className="loginField">
            <label htmlFor="money-account">
              {mode === "transfer" ? "From" : "Account"}
            </label>
            <select
              id="money-account"
              className="loginInput"
              value={accountId}
              onChange={(event) => setAccountId(event.target.value)}
            >
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>{account.name}</option>
              ))}
            </select>
          </div>

          {mode === "transfer" && (
            <div className="loginField">
              <label htmlFor="money-to">To</label>
              <select
                id="money-to"
                className="loginInput"
                value={toAccountId}
                onChange={(event) => setToAccountId(event.target.value)}
              >
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>{account.name}</option>
                ))}
              </select>
            </div>
          )}

          <div className="loginField">
            <label htmlFor="money-amount">Amount</label>
            <input
              id="money-amount"
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
            <label htmlFor="money-description">Description</label>
            <input
              id="money-description"
              className="loginInput"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder={mode === "transfer" ? "Optional" : "e.g. Groceries"}
            />
          </div>

          <div className="loginField">
            <label htmlFor="money-date">Date</label>
            <input
              id="money-date"
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
              {submitting ? "Saving..." : "Record"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
