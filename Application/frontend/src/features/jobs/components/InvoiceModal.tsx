import { useState } from "react";
import Modal from "../../../shared/components/Modal";
import { getErrorMessage } from "../../grades/components/AddCourseModal";
import { createClient, createInvoice, updateInvoice } from "../api";
import { Client, Invoice } from "../types";
import { today } from "../../../shared/utils/dateUtils";

/** Select value meaning "a client not on the list yet". */
const NEW = "__new__";

/** Props for the invoice editor. */
interface Props {
  readonly userId: string;
  /** The invoice being corrected; null for a new one. */
  readonly invoice: Invoice | null;
  readonly clients: readonly Client[];
  /** Suggested number for a new invoice. */
  readonly nextNumber: string;
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

/**
 * Write or correct an invoice: client (or a new one), number, amount, dates, what it was for.
 * Due date left blank means 30 days after issue.
 */
export default function InvoiceModal({ userId, invoice, clients, nextNumber, onClose, onSaved }: Props) {
  const offered = clients.filter((c) => !c.archived || c.id === invoice?.client_id);
  const [clientId, setClientId] = useState(invoice?.client_id ?? offered[0]?.id ?? NEW);
  const [newClient, setNewClient] = useState("");
  const [number, setNumber] = useState(invoice?.number ?? nextNumber);
  const [amount, setAmount] = useState(invoice ? String(invoice.amount) : "");
  const [issuedOn, setIssuedOn] = useState(invoice?.issued_on ?? today());
  const [dueOn, setDueOn] = useState(invoice?.due_on ?? "");
  const [description, setDescription] = useState(invoice?.description ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      let client = clientId;
      if (client === NEW) client = (await createClient(userId, newClient.trim())).id;
      const body = {
        client_id: client, number: number.trim(), amount: Number(amount), issued_on: issuedOn,
        description: description.trim() || null, ...(dueOn ? { due_on: dueOn } : {}),
      };
      if (invoice) await updateInvoice(userId, invoice.id, body);
      else await createInvoice(userId, body);
      onSaved();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title={invoice ? `Edit invoice ${invoice.number}` : "New invoice"} onClose={onClose}>
      <form className="loginForm" onSubmit={handleSubmit}>
        <div className="loginField">
          <label htmlFor="invoice-client">Client</label>
          <select id="invoice-client" className="loginInput" value={clientId}
            onChange={(event) => setClientId(event.target.value)}>
            {offered.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            <option value={NEW}>New client...</option>
          </select>
        </div>
        {clientId === NEW && (
          <div className="loginField">
            <label htmlFor="invoice-new-client">New client&rsquo;s name</label>
            <input id="invoice-new-client" className="loginInput" maxLength={80} required value={newClient}
              onChange={(event) => setNewClient(event.target.value)} />
          </div>
        )}
        <div className="loginField">
          <label htmlFor="invoice-number">Invoice number</label>
          <input id="invoice-number" className="loginInput" maxLength={40} required value={number}
            onChange={(event) => setNumber(event.target.value)} />
        </div>
        <div className="loginField">
          <label htmlFor="invoice-amount">Amount</label>
          <input id="invoice-amount" className="loginInput" type="number" min={0.01} max={1000000} step="0.01"
            required value={amount} onChange={(event) => setAmount(event.target.value)} />
        </div>
        <div className="loginField">
          <label htmlFor="invoice-issued">Issued</label>
          <input id="invoice-issued" className="loginInput" type="date" required value={issuedOn}
            onChange={(event) => setIssuedOn(event.target.value)} />
        </div>
        <div className="loginField">
          <label htmlFor="invoice-due">Due (blank: 30 days after issue)</label>
          <input id="invoice-due" className="loginInput" type="date" min={issuedOn} value={dueOn}
            onChange={(event) => setDueOn(event.target.value)} />
        </div>
        <div className="loginField">
          <label htmlFor="invoice-description">What it was for</label>
          <input id="invoice-description" className="loginInput" maxLength={200} value={description}
            onChange={(event) => setDescription(event.target.value)} />
        </div>
        {error && <p className="loginError">{error}</p>}
        <div className="flex justify-end gap-3 pt-2">
          <button type="button" onClick={onClose} disabled={saving}
            className="rounded-lg border border-slate-700 !bg-slate-900 !text-slate-200">Cancel</button>
          <button type="submit" className="loginSubmit" disabled={saving}>{saving ? "Saving..." : "Save"}</button>
        </div>
      </form>
    </Modal>
  );
}
