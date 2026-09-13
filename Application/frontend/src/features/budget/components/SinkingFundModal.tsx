import { useEffect, useState } from "react";
import Modal from "../../../shared/components/Modal";
import { createSinkingFund } from "../api";
import { Account, SinkingFundCreate } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";
import { addDays, today } from "../../../shared/utils/dateUtils";

interface SinkingFundModalProps {
  readonly open: boolean;
  readonly accounts: Account[];
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

function blank(accounts: Account[]): SinkingFundCreate {
  // Defaults that are usually right: out of a spending account, into the first
  // account that is not one.
  const spending = accounts.find((a) => a.kind === "spending") ?? accounts[0];
  const elsewhere = accounts.find((a) => a.id !== spending?.id);

  return {
    name: "",
    target_amount: 0,
    due_on: addDays(today(), 90),
    from_account_id: spending?.id ?? "",
    to_account_id: elsewhere?.id ?? "",
    archived: false,
  };
}

/**
 * Creating a fund.
 *
 * Only four things are asked, because only four are needed: what it costs, when
 * it is due, and the two accounts the money moves between. The monthly figure is
 * not asked for — it is the division of the first two, and asking would invite
 * a schedule that disagrees with the target.
 */
export default function SinkingFundModal({
  open,
  accounts,
  onClose,
  onSaved,
}: SinkingFundModalProps) {
  const { user } = useAuth();
  const [form, setForm] = useState<SinkingFundCreate>(blank(accounts));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setForm(blank(accounts));
    setError(null);
  }, [open, accounts]);

  if (!open) return null;

  function update<K extends keyof SinkingFundCreate>(key: K, value: SinkingFundCreate[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;

    setSaving(true);
    setError(null);
    try {
      await createSinkingFund(user.id, { ...form, name: form.name.trim() });
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create that fund");
    } finally {
      setSaving(false);
    }
  }

  const months = monthsUntil(form.due_on);
  const perMonth = months > 0 ? form.target_amount / months : form.target_amount;

  return (
    <Modal title="Set money aside" onClose={onClose}>
      <form className="calForm" onSubmit={handleSubmit}>
        <label className="calField">
          <span className="calFieldLabel">For</span>
          <input
            className="calInput"
            value={form.name}
            onChange={(event) => update("name", event.target.value)}
            placeholder="Tuition, January"
            required
          />
        </label>

        <div className="calRow">
          <label className="calField">
            <span className="calFieldLabel">Amount</span>
            <input
              type="number"
              min={0}
              step="any"
              className="calInput"
              value={form.target_amount || ""}
              onChange={(event) => update("target_amount", Number(event.target.value) || 0)}
              placeholder="2400.00"
              required
            />
          </label>

          <label className="calField">
            <span className="calFieldLabel">Due</span>
            <input
              type="date"
              className="calInput"
              value={form.due_on}
              onChange={(event) => update("due_on", event.target.value)}
              required
            />
          </label>
        </div>

        <div className="calRow">
          <label className="calField">
            <span className="calFieldLabel">From</span>
            <select
              className="calInput"
              value={form.from_account_id}
              onChange={(event) => update("from_account_id", event.target.value)}
              required
            >
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>{account.name}</option>
              ))}
            </select>
          </label>

          <label className="calField">
            <span className="calFieldLabel">Into</span>
            <select
              className="calInput"
              value={form.to_account_id}
              onChange={(event) => update("to_account_id", event.target.value)}
              required
            >
              {accounts
                .filter((account) => account.id !== form.from_account_id)
                .map((account) => (
                  <option key={account.id} value={account.id}>{account.name}</option>
                ))}
            </select>
          </label>
        </div>

        {/* Shown, not asked for. The figure is the division of the two fields
            above, and a box to type it in would invite a schedule that
            disagrees with the target it is meant to reach. */}
        {form.target_amount > 0 && (
          <p className="small-text muted">
            About {perMonth.toFixed(2)} a month over {months || 1}{" "}
            {months === 1 ? "month" : "months"}. Recalculated as you go, so a
            missed month raises the rest rather than moving the date.
          </p>
        )}

        {error && <p className="calError">{error}</p>}

        <div className="calFormActions">
          <button type="button" className="calButton" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className="calButton calButtonPrimary" disabled={saving}>
            {saving ? "Saving…" : "Create fund"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** Whole calendar months from today to the due date, counting this one. */
function monthsUntil(due: string): number {
  const now = new Date();
  const [year, month] = due.split("-").map(Number);
  const diff = (year - now.getFullYear()) * 12 + (month - 1 - now.getMonth());
  return Math.max(0, diff) + 1;
}
