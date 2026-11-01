import { useState } from "react";
import Modal from "../../../shared/components/Modal";
import { getErrorMessage } from "../../grades/components/AddCourseModal";
import { markInvoicePaid } from "../api";
import { Invoice } from "../types";
import { Account } from "../../budget/types";
import { formatMoney } from "../../budget/money";
import { today } from "../../../shared/utils/dateUtils";

/** Where the payment goes: nowhere new, split by income share, or one account's id. */
const ALREADY = "__already__";
const SPLIT = "__split__";

/** Props for the mark-paid dialog. */
interface Props {
  readonly userId: string;
  readonly invoice: Invoice;
  readonly accounts: readonly Account[];
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

/**
 * Mark an invoice paid: the day it arrived, and whether to record it in an account,
 * split it by income share, or leave the ledger alone because it's already there.
 */
export default function InvoicePaidModal({ userId, invoice, accounts, onClose, onSaved }: Props) {
  const open = accounts.filter((a) => !a.archived);
  const [paidOn, setPaidOn] = useState(today() < invoice.issued_on ? invoice.issued_on : today());
  const [where, setWhere] = useState(open[0]?.id ?? ALREADY);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await markInvoicePaid(userId, invoice.id, {
        paid_on: paidOn,
        ...(where === SPLIT ? { split: true } : where === ALREADY ? {} : { account_id: where }),
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title={`Invoice ${invoice.number} paid`} onClose={onClose}>
      <p className="small-text">{formatMoney(invoice.amount)} from {invoice.client}.</p>
      <form className="loginForm" onSubmit={handleSubmit}>
        <div className="loginField">
          <label htmlFor="paid-on">Paid on</label>
          <input id="paid-on" className="loginInput" type="date" min={invoice.issued_on} required value={paidOn}
            onChange={(event) => setPaidOn(event.target.value)} />
        </div>
        <div className="loginField">
          <label htmlFor="paid-where">Record it in</label>
          <select id="paid-where" className="loginInput" value={where} onChange={(event) => setWhere(event.target.value)}>
            {open.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            <option value={SPLIT}>Split by income share</option>
            <option value={ALREADY}>Already in my money (record nothing new)</option>
          </select>
        </div>
        {error && <p className="loginError">{error}</p>}
        <div className="flex justify-end gap-3 pt-2">
          <button type="button" onClick={onClose} disabled={saving}
            className="rounded-lg border border-slate-700 !bg-slate-900 !text-slate-200">Cancel</button>
          <button type="submit" className="loginSubmit" disabled={saving}>{saving ? "Saving..." : "Mark paid"}</button>
        </div>
      </form>
    </Modal>
  );
}
