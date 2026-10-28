import { useEffect, useState } from "react";
import Modal from "../../../shared/components/Modal";
import RecurrenceEditor from "../../calender/components/RecurrenceEditor";
import { createRecurring, updateRecurring } from "../api";
import {
  Account,
  RecurringCreate,
  RecurringKind,
  RecurringTransaction,
  SpendCategory,
} from "../types";
import { useAuth } from "../../../app/auth/AuthContext";
import { today } from "../../../shared/utils/dateUtils";

/** Display label per kind. */
const KIND_LABELS: Record<RecurringKind, string> = {
  expense: "Expense",
  income: "Income",
  transfer: "Transfer",
  deposit: "Deposit",
};

/** What each kind does when it repeats, shown under the picker. */
const KIND_HINTS: Record<RecurringKind, string> = {
  expense: "Leaves the account on each date — rent, a subscription.",
  income: "Arrives in one account on each date.",
  transfer: "Moves between two of your accounts on each date.",
  deposit: "Splits across your accounts by income share, worked out on the day.",
};

/** Props for the standing-instruction dialog. */
interface RecurringModalProps {
  readonly open: boolean;
  /** The instruction being edited, or null for a new one. */
  readonly rule: RecurringTransaction | null;
  readonly accounts: Account[];
  readonly categories: SpendCategory[];
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

/** A new monthly expense from the first account, starting today. */
function blankRule(accounts: Account[]): RecurringCreate {
  return {
    kind: "expense",
    amount: 0,
    description: null,
    account_id: accounts[0]?.id ?? null,
    to_account_id: null,
    category_id: null,
    starts_on: today(),
    // Monthly by default: almost everything that recurs with money is monthly,
    // and the editor below can change it.
    recurrence: { freq: "monthly", interval: 1, byday: [], until: null, count: null },
    active: true,
  };
}

/** The form's starting values: the rule's own, or a blank one. */
function formFor(rule: RecurringTransaction | null, accounts: Account[]): RecurringCreate {
  if (!rule) return blankRule(accounts);

  return {
    kind: rule.kind,
    amount: rule.amount,
    description: rule.description,
    account_id: rule.account_id,
    to_account_id: rule.to_account_id,
    category_id: rule.category_id,
    starts_on: rule.starts_on,
    recurrence: rule.recurrence,
    active: rule.active,
  };
}

/**
 * Create or edit a standing instruction; its kind and accounts cannot change once it exists.
 * Changing kind clears the fields that kind cannot carry.
 */
export default function RecurringModal({
  open,
  rule,
  accounts,
  categories,
  onClose,
  onSaved,
}: RecurringModalProps) {
  const { user } = useAuth();
  const [form, setForm] = useState<RecurringCreate>(formFor(rule, accounts));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setForm(formFor(rule, accounts));
    setError(null);
  }, [rule, accounts, open]);

  if (!open) return null;

  function update<K extends keyof RecurringCreate>(key: K, value: RecurringCreate[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  /**
   * Switching kind clears the fields that kind cannot carry.
   *
   * The server rejects a deposit that names an account, or income carrying a
   * spending category. Clearing here means the form cannot be submitted in a
   * shape the server has already said is meaningless.
   */
  function changeKind(kind: RecurringKind) {
    setForm((current) => ({
      ...current,
      kind,
      account_id: kind === "deposit" ? null : current.account_id ?? accounts[0]?.id ?? null,
      to_account_id: kind === "transfer" ? current.to_account_id : null,
      category_id: kind === "expense" ? current.category_id : null,
    }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;

    setSaving(true);
    setError(null);
    try {
      if (rule) {
        // Kind and accounts are fixed once payments exist against a rule:
        // changing what a standing instruction *is* would rewrite the meaning
        // of the history it has already written.
        await updateRecurring(user.id, rule.id, {
          amount: form.amount,
          description: form.description,
          category_id: form.category_id,
          starts_on: form.starts_on,
          recurrence: form.recurrence,
          active: form.active,
        });
      } else {
        await createRecurring(user.id, form);
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save this");
    } finally {
      setSaving(false);
    }
  }

  const spendable = accounts.filter((account) => !account.archived);

  return (
    <Modal
      title={rule ? "Edit standing instruction" : "New standing instruction"}
      onClose={onClose}
      panelClassName="widePopup"
    >
      <form className="calForm" onSubmit={handleSubmit}>
        {!rule && (
          <div className="moneyTabs" role="group" aria-label="What kind of movement">
            {(Object.keys(KIND_LABELS) as RecurringKind[]).map((kind) => (
              <button
                key={kind}
                type="button"
                className={form.kind === kind ? "moneyTab moneyTabActive" : "moneyTab"}
                onClick={() => changeKind(kind)}
                aria-pressed={form.kind === kind}
              >
                {KIND_LABELS[kind]}
              </button>
            ))}
          </div>
        )}
        <p className="calHint">{KIND_HINTS[form.kind]}</p>

        <div className="calRow">
          {form.kind !== "deposit" && (
            <label className="calField">
              <span className="calFieldLabel">{form.kind === "transfer" ? "From" : "Account"}</span>
              <select
                className="calInput"
                value={form.account_id ?? ""}
                onChange={(event) => update("account_id", event.target.value || null)}
                disabled={Boolean(rule)}
                required
              >
                {spendable.map((account) => (
                  <option key={account.id} value={account.id}>{account.name}</option>
                ))}
              </select>
            </label>
          )}

          {form.kind === "transfer" && (
            <label className="calField">
              <span className="calFieldLabel">To</span>
              <select
                className="calInput"
                value={form.to_account_id ?? ""}
                onChange={(event) => update("to_account_id", event.target.value || null)}
                disabled={Boolean(rule)}
                required
              >
                <option value="">Choose</option>
                {spendable
                  .filter((account) => account.id !== form.account_id)
                  .map((account) => (
                    <option key={account.id} value={account.id}>{account.name}</option>
                  ))}
              </select>
            </label>
          )}

          <label className="calField">
            <span className="calFieldLabel">Amount</span>
            <input
              type="number"
              min={0.01}
              step={0.01}
              className="calInput"
              value={form.amount || ""}
              onChange={(event) => update("amount", Number(event.target.value))}
              required
            />
          </label>
        </div>

        {form.kind === "expense" && categories.length > 0 && (
          <label className="calField">
            <span className="calFieldLabel">Category</span>
            <select
              className="calInput"
              value={form.category_id ?? ""}
              onChange={(event) => update("category_id", event.target.value || null)}
            >
              <option value="">Uncategorised</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>{category.name}</option>
              ))}
            </select>
          </label>
        )}

        <label className="calField">
          <span className="calFieldLabel">Description</span>
          <input
            className="calInput"
            value={form.description ?? ""}
            onChange={(event) => update("description", event.target.value || null)}
            placeholder="Rent, Spotify, student loan"
          />
        </label>

        <label className="calField">
          <span className="calFieldLabel">First payment</span>
          <input
            type="date"
            className="calInput"
            value={form.starts_on}
            onChange={(event) => update("starts_on", event.target.value)}
            required
          />
        </label>

        <RecurrenceEditor
          value={form.recurrence}
          onChange={(recurrence) =>
            // A standing instruction that does not repeat is just a payment, so
            // the rule always keeps a frequency; clearing it falls back to monthly.
            update("recurrence", recurrence ?? {
              freq: "monthly", interval: 1, byday: [], until: null, count: null,
            })
          }
          startsOn={form.starts_on}
        />

        <label className="taskToggle">
          <input
            type="checkbox"
            checked={form.active}
            onChange={(event) => update("active", event.target.checked)}
          />
          Active — uncheck to pause without losing the history
        </label>

        {error && <p className="calError">{error}</p>}

        <div className="calFormActions">
          <button type="button" className="calButton" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className="calButton calButtonPrimary" disabled={saving}>
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
