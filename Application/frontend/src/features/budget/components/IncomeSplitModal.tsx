import { useEffect, useState } from "react";
import { updateAccount } from "../api";
import { Account } from "../types";
import { getErrorMessage } from "../../grades/components/AddCourseModal";
import { useAuth } from "../../../app/auth/AuthContext";
import Modal from "../../../shared/components/Modal";
import HelpTip from "../../../shared/components/HelpTip";

/** Props for the income split dialog. */
interface IncomeSplitModalProps {
  readonly open: boolean;
  readonly accounts: readonly Account[];
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

/**
 * Every account's income share on one screen, as ratios with each one's percent.
 * Saves one PATCH per changed account; a zero total cannot be saved.
 */
export default function IncomeSplitModal({
  open,
  accounts,
  onClose,
  onSaved,
}: IncomeSplitModalProps) {
  const { user } = useAuth();
  const [shares, setShares] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setShares(
      Object.fromEntries(accounts.map((a) => [a.id, String(a.income_share)]))
    );
  }, [open, accounts]);

  if (!open) return null;

  const total = Object.values(shares).reduce((sum, value) => sum + Number(value || 0), 0);
  // Income divides by ratio, so any positive total works. Zero does not: there
  // would be nowhere for a deposit to land, and `record_deposit` refuses it.
  // Better to say so here than to let someone save it and find out later.
  const nothingShared = total <= 0;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user || nothingShared) return;

    setSubmitting(true);
    setError(null);
    try {
      // One PATCH per changed account. A partial failure is survivable here
      // and only here: these are ratios, so what lands is still a valid split,
      // just not the intended one.
      const changed = accounts.filter(
        (a) => Number(shares[a.id] ?? a.income_share) !== a.income_share
      );
      for (const account of changed) {
        await updateAccount(user.id, account.id, {
          income_share: Number(shares[account.id] || 0),
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
    <Modal title="Income split" onClose={onClose}>
      <form className="loginForm" onSubmit={handleSubmit}>
        <HelpTip label="How the split works">
          Money you record as income divides between these by ratio, so the shares
          need not total 100 — only their sizes relative to each other matter.
        </HelpTip>

        <ul className="splitList">
          {accounts.map((account) => {
            const value = Number(shares[account.id] || 0);
            const portion = total > 0 ? (value / total) * 100 : 0;
            return (
              <li className="splitRow" key={account.id}>
                <label className="splitName" htmlFor={`split-${account.id}`}>
                  {account.name}
                </label>
                <input
                  id={`split-${account.id}`}
                  className="loginInput splitInput"
                  type="number"
                  min={0}
                  max={100}
                  step="0.1"
                  value={shares[account.id] ?? "0"}
                  onChange={(event) =>
                    setShares((prev) => ({ ...prev, [account.id]: event.target.value }))
                  }
                />
                {/* What the number actually means once the ratio is applied --
                    the thing a single share in isolation cannot tell you. */}
                <span className="splitPortion small-text muted">
                  {portion.toFixed(1)}% of income
                </span>
              </li>
            );
          })}
        </ul>

        <p className={nothingShared ? "loginError" : "loginHint"} role={nothingShared ? "alert" : undefined}>
          {nothingShared
            ? "Give at least one account a share, or income has nowhere to go."
            : `Shares total ${total.toFixed(1)}%`}
        </p>

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
          <button type="submit" className="loginSubmit" disabled={submitting || nothingShared}>
            {submitting ? "Saving..." : "Save split"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
