import { useEffect, useState } from "react";
import { createAccount, deleteAccount, updateAccount } from "../api";
import { Account, AccountKind } from "../types";
import { getErrorMessage } from "../../grades/components/AddCourseModal";
import { useAuth } from "../../../app/auth/AuthContext";
import Modal from "../../../shared/components/Modal";
import HelpTip from "../../../shared/components/HelpTip";
import { COUNTED_HELP, COUNTED_LABEL } from "../counting";

/** Props for the account dialog. */
interface EditAccountModalProps {
  readonly account: Account | null;
  /** Open in create mode; `account` is ignored while set. */
  readonly creating?: boolean;
  readonly accounts: readonly Account[];
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

/** Account kinds in picker order. */
const KINDS: AccountKind[] = [
  "spending",
  "savings",
  "investment",
  "emergency",
  "other",
  "debt",
];

/** One-line hint under the kind picker, for the kinds that need one. */
const KIND_HINTS: Partial<Record<AccountKind, string>> = {
  spending: "Safe to spend reads from these.",
  debt: "Money you owe. Its balance runs negative, and it lowers your total.",
};

/**
 * Add or edit an account: name, kind, income share, counted switch, archive, delete.
 * Delete asks in the dialog first; a role-locked account cannot be deleted, archived or re-kinded.
 */
export default function EditAccountModal({
  account,
  creating = false,
  accounts,
  onClose,
  onSaved,
}: EditAccountModalProps) {
  const { user } = useAuth();
  const [name, setName] = useState("");
  const [kind, setKind] = useState<AccountKind>("other");
  const [share, setShare] = useState("0");
  const [archived, setArchived] = useState(false);
  const [counts, setCounts] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Delete used to fire on the first click, from the leftmost button in the row,
  // with no confirmation at all -- alone among every delete in the app. The
  // server refuses while the account still holds transactions, so the exposure
  // is an empty account, but there is no undo.
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  useEffect(() => {
    setError(null);
    setConfirmingDelete(false);

    if (creating) {
      setName("");
      setKind("other");
      setShare("0");
      setArchived(false);
      setCounts(true);
      return;
    }
    if (!account) return;
    setName(account.name);
    setKind(account.kind);
    setShare(String(account.income_share));
    setArchived(account.archived);
    setCounts(account.counts_toward_net_worth);
  }, [account, creating]);

  if (!creating && !account) return null;

  // The last account of a kind the app depends on. The server refuses to
  // delete, archive or re-kind it; saying so on the disabled control is the
  // difference between a rule and a dead end.
  const locked = !creating && account?.role_locked === true;
  const lockReason = locked
    ? `${account?.name} is your only ${account?.kind} account. Create another one first.`
    : undefined;

  // What the shares would total if this change were saved. Income is split by
  // ratio, so anything other than 100 still works -- it is just harder to
  // reason about, which is worth saying rather than blocking.
  const othersTotal = accounts.reduce(
    (sum, item) => (item.id === account?.id && !creating ? sum : sum + item.income_share),
    0
  );
  const projectedTotal = othersTotal + Number(share || 0);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;

    setSubmitting(true);
    setError(null);
    try {
      if (creating) {
        await createAccount(user.id, {
          name,
          kind,
          income_share: Number(share || 0),
          archived: false,
          position: accounts.length,
          counts_toward_net_worth: counts,
        });
      } else if (account) {
        await updateAccount(user.id, account.id, {
          name,
          kind,
          income_share: Number(share || 0),
          archived,
          counts_toward_net_worth: counts,
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

  async function handleDelete() {
    if (!user || !account) return;

    setSubmitting(true);
    setError(null);
    try {
      await deleteAccount(user.id, account.id);
      onSaved();
      onClose();
    } catch (err) {
      // The server refuses while the account holds history, while anything
      // still points at it, and while it is the last of its role.
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal title={creating ? "Add account" : "Edit account"} onClose={onClose}>

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
            disabled={locked}
            title={lockReason}
            onChange={(event) => setKind(event.target.value as AccountKind)}
          >
            {KINDS.map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
          {KIND_HINTS[kind] && (
            <span className="loginHint">{KIND_HINTS[kind]}</span>
          )}
          {locked && <span className="loginHint">{lockReason}</span>}
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

        {/* Available on every kind. One switch for net worth and every
            analytic (D39); the same words as the list in Settings. */}
        <div className="settingsToggle">
          <input
            id="account-counts"
            type="checkbox"
            checked={counts}
            onChange={(event) => setCounts(event.target.checked)}
          />
          <span className="labelWithTip">
            <label htmlFor="account-counts">{COUNTED_LABEL}</label>
            <HelpTip label="When to turn this off">{COUNTED_HELP}</HelpTip>
          </span>
        </div>

        {/* Neither belongs on a form for something that does not exist yet. */}
        {!creating && (
          <div className="settingsToggle">
            <input
              id="account-archived"
              type="checkbox"
              checked={archived}
              disabled={locked}
              onChange={(event) => setArchived(event.target.checked)}
            />
            <span className="labelWithTip">
              <label htmlFor="account-archived">Archive</label>
              <HelpTip label="What archiving does">
                Keeps the account and its history but stops offering it when you record
                something. Reversible, unlike deleting it.
              </HelpTip>
            </span>
          </div>
        )}

        {error && <p className="loginError">{error}</p>}

        {confirmingDelete && (
          <p className="loginError" role="alert">
            Delete <strong>{account?.name}</strong> permanently? This cannot be undone.
          </p>
        )}

        <div className="flex items-center justify-between gap-3 pt-2">
          {/* Kept away from Save and Cancel, so a misclick on the pair you reach
              for twenty times a day cannot land on the destructive one. */}
          <div className="flex gap-3">
            {!creating && (confirmingDelete ? (
              <>
                <button
                  type="button"
                  onClick={handleDelete}
                  className="rounded-lg !bg-red-600 !text-white"
                  disabled={submitting}
                >
                  {submitting ? "Deleting..." : "Yes, delete"}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmingDelete(false)}
                  className="rounded-lg border border-slate-700 !bg-slate-900 !text-slate-200"
                  disabled={submitting}
                >
                  Keep it
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmingDelete(true)}
                className="rounded-lg !bg-red-600 !text-white"
                disabled={submitting || locked}
                title={lockReason}
              >
                Delete
              </button>
            ))}
          </div>

          <div className="flex gap-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700 !bg-slate-900 !text-slate-200"
              disabled={submitting}
            >
              Cancel
            </button>
            <button type="submit" className="loginSubmit" disabled={submitting}>
              {submitting ? "Saving..." : creating ? "Add account" : "Save"}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  );
}
