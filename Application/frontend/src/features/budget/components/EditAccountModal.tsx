import { useEffect, useState } from "react";
import { deleteAccount, updateAccount } from "../api";
import { Account, AccountKind } from "../types";
import { getErrorMessage } from "../../grades/components/AddCourseModal";
import { useAuth } from "../../../app/auth/AuthContext";

interface EditAccountModalProps {
  readonly account: Account | null;
  readonly accounts: readonly Account[];
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

const KINDS: AccountKind[] = ["spending", "savings", "investment", "emergency", "other"];

export default function EditAccountModal({
  account,
  accounts,
  onClose,
  onSaved,
}: EditAccountModalProps) {
  const { user } = useAuth();
  const [name, setName] = useState("");
  const [kind, setKind] = useState<AccountKind>("other");
  const [share, setShare] = useState("0");
  const [archived, setArchived] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!account) return;
    setName(account.name);
    setKind(account.kind);
    setShare(String(account.income_share));
    setArchived(account.archived);
    setError(null);
  }, [account]);

  if (!account) return null;

  // What the shares would total if this change were saved. Income is split by
  // ratio, so anything other than 100 still works -- it is just harder to
  // reason about, which is worth saying rather than blocking.
  const projectedTotal = accounts.reduce(
    (sum, item) => sum + (item.id === account.id ? Number(share || 0) : item.income_share),
    0
  );

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user || !account) return;

    setSubmitting(true);
    setError(null);
    try {
      await updateAccount(user.id, account.id, {
        name,
        kind,
        income_share: Number(share || 0),
        archived,
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete() {
    if (!user || !account) return;

    setSubmitting(true);
    setError(null);
    try {
      await deleteAccount(user.id, account.id);
      onSaved();
      onClose();
    } catch (err) {
      // The server refuses while the account still holds transactions, and
      // says to archive instead.
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="popup">
      <div className="addCoursePopup">
        <h2>Edit account</h2>

        <form className="loginForm" onSubmit={handleSubmit}>
          <div className="loginField">
            <label htmlFor="account-name">Name</label>
            <input
              id="account-name"
              className="loginInput"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
            />
          </div>

          <div className="loginField">
            <label htmlFor="account-kind">Kind</label>
            <select
              id="account-kind"
              className="loginInput"
              value={kind}
              onChange={(event) => setKind(event.target.value as AccountKind)}
            >
              {KINDS.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </div>

          <div className="loginField">
            <label htmlFor="account-share">Share of income (%)</label>
            <input
              id="account-share"
              className="loginInput"
              type="number"
              min={0}
              max={100}
              step="0.1"
              value={share}
              onChange={(event) => setShare(event.target.value)}
            />
            <span className={projectedTotal === 100 ? "loginHint" : "loginHint shareWarning"}>
              Shares would total {projectedTotal.toFixed(1)}%
              {projectedTotal !== 100 && " — income is split by ratio, so this still works"}
            </span>
          </div>

          <div className="settingsToggle">
            <input
              id="account-archived"
              type="checkbox"
              checked={archived}
              onChange={(event) => setArchived(event.target.checked)}
            />
            <label htmlFor="account-archived">
              Archive
              <span className="small-text muted">
                {" "}— keeps its history but stops offering it
              </span>
            </label>
          </div>

          {error && <p className="loginError">{error}</p>}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={handleDelete}
              className="rounded-lg !bg-red-600 !text-white"
              disabled={submitting}
            >
              Delete
            </button>
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
