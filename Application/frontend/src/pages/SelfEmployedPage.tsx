import { useCallback, useEffect, useState } from "react";
import JobsTabs from "../features/jobs/components/JobsTabs";
import InvoiceModal from "../features/jobs/components/InvoiceModal";
import InvoicePaidModal from "../features/jobs/components/InvoicePaidModal";
import CraWatch from "../features/jobs/components/CraWatch";
import BusinessExpenses from "../features/jobs/components/BusinessExpenses";
import DeleteConfirmModal from "../features/grades/components/DeleteConfirmModal";
import {
  deleteClient, deleteInvoice, fetchClients, fetchInvoices, fetchSelfEmployment, markInvoiceUnpaid, updateClient,
} from "../features/jobs/api";
import { fetchAccounts } from "../features/budget/api";
import { Account } from "../features/budget/types";
import { Client, Invoice, SelfEmployment } from "../features/jobs/types";
import { formatMoney } from "../features/budget/money";
import { shortDate } from "../shared/utils/dateUtils";
import { useAuth } from "../app/auth/AuthContext";
import "../styles/calendar.css";
import "../styles/jobs.css";
import "../styles/selfEmployed.css";

/** How an invoice's state reads in its badge. */
function stateLabel(invoice: Invoice) {
  if (invoice.state === "paid") return `Paid ${shortDate(invoice.paid_on as string)}`;
  if (invoice.state === "overdue") return `${invoice.days_overdue} ${invoice.days_overdue === 1 ? "day" : "days"} overdue`;
  return `Due ${shortDate(invoice.due_on)}`;
}

/**
 * Self-employment (Phase 4 item 15): invoices and their states, clients, the year's
 * figures, the CRA rules read against them, and business expenses. Not an accounting
 * product: it stops at what a student freelancer needs to stay out of trouble.
 */
export default function SelfEmployedPage() {
  const { user } = useAuth();
  const userId = user?.id;
  const [year, setYear] = useState<SelfEmployment | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Invoice | null>(null);
  const [composing, setComposing] = useState(false);
  const [paying, setPaying] = useState<Invoice | null>(null);
  const [deleting, setDeleting] = useState<Invoice | null>(null);
  const [deletingClient, setDeletingClient] = useState<Client | null>(null);
  const [showPaid, setShowPaid] = useState(false);

  const load = useCallback(async () => {
    if (!userId) return;
    try {
      const [found, list, people, money] = await Promise.all([
        fetchSelfEmployment(userId), fetchInvoices(userId), fetchClients(userId), fetchAccounts(userId),
      ]);
      setYear(found);
      setInvoices(list);
      setClients(people);
      setAccounts(money);
      setError(null);
    } catch {
      setError("Couldn't load your invoices.");
    }
  }, [userId]);

  useEffect(() => { load(); }, [load]);

  async function act(call: () => Promise<unknown>) {
    try {
      await call();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "That didn't work.");
    }
  }

  if (!userId) return null;
  const open = invoices.filter((i) => i.state !== "paid");
  const paid = invoices.filter((i) => i.state === "paid");

  function row(invoice: Invoice) {
    return (
      <li key={invoice.id} className={`seInvoice seInvoice-${invoice.state}`}>
        <button type="button" className="seInvoiceMain" onClick={() => setEditing(invoice)}>
          <span className="seInvoiceTitle">{invoice.number} · {invoice.client}</span>
          <span className="small-text muted">
            Issued {shortDate(invoice.issued_on)}{invoice.description ? ` · ${invoice.description}` : ""}
          </span>
        </button>
        <span className="seInvoiceAmount">{formatMoney(invoice.amount)}</span>
        <span className={`seBadge seBadge-${invoice.state}`}>{stateLabel(invoice)}</span>
        <span className="seInvoiceActions">
          {invoice.state === "paid" ? (
            <button type="button" className="seLink" onClick={() => act(() => markInvoiceUnpaid(userId as string, invoice.id))}>
              Mark unpaid
            </button>
          ) : (
            <button type="button" className="calButton" onClick={() => setPaying(invoice)}>Mark paid</button>
          )}
          <button type="button" className="seLink" onClick={() => setDeleting(invoice)}
            aria-label={`Delete invoice ${invoice.number}`}>Delete</button>
        </span>
      </li>
    );
  }

  return (
    <div className="container">
      <div className="calTopbar">
        <h1 className="title">Jobs</h1>
        <button type="button" className="calButton calButtonPrimary" onClick={() => { setEditing(null); setComposing(true); }}>
          New invoice
        </button>
      </div>
      <JobsTabs />
      {error && <p className="loginError">{error}</p>}

      {year && (
        <>
          {year.overdue.length > 0 && (
            <section className="seCard seOverdue" aria-label="Overdue invoices">
              <h2 className="seHeading">
                {year.overdue.length === 1 ? "An invoice is overdue" : `${year.overdue.length} invoices are overdue`}
              </h2>
              <ul className="seList">
                {year.overdue.map((i) => (
                  <li key={i.id} className="seRow">
                    <span className="seRowMain">{i.number} to {i.client}: {formatMoney(i.amount)}</span>
                    <span className="small-text">{stateLabel(i)}</span>
                    <button type="button" className="calButton" onClick={() => setPaying(i)}>Mark paid</button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="seFigures" aria-label={`${year.year} so far`}>
            <div className="seFigure"><span className="seFigureValue">{formatMoney(year.revenue, { whole: true })}</span>
              <span className="seFigureLabel">Invoiced in {year.year}</span></div>
            <div className="seFigure"><span className="seFigureValue">{formatMoney(year.received, { whole: true })}</span>
              <span className="seFigureLabel">Paid to you</span></div>
            <div className="seFigure"><span className="seFigureValue">{formatMoney(year.business_expenses, { whole: true })}</span>
              <span className="seFigureLabel">Business expenses</span></div>
            <div className="seFigure"><span className="seFigureValue">{formatMoney(year.net, { whole: true })}</span>
              <span className="seFigureLabel">Net self-employment</span></div>
            <div className="seFigure"><span className="seFigureValue">{formatMoney(year.unpaid, { whole: true })}</span>
              <span className="seFigureLabel">Waiting to be paid</span></div>
          </section>
          {year.typical_month && (
            <p className="small-text seTypical">
              A month typically brings in {formatMoney(year.typical_month.low, { whole: true })}&ndash;
              {formatMoney(year.typical_month.high, { whole: true })}, over the last {year.typical_month.months} months:
              a range, because self-employed income is never one number.
            </p>
          )}
        </>
      )}

      <section className="seCard" aria-label="Invoices">
        <h2 className="seHeading">Invoices</h2>
        {invoices.length === 0 && (
          <p className="small-text muted">
            No invoices yet. Tutoring, design, a gig: write one with New invoice, and it&rsquo;s tracked until it&rsquo;s paid.
          </p>
        )}
        {open.length > 0 && <ul className="seInvoices">{open.map(row)}</ul>}
        {paid.length > 0 && (
          <>
            <button type="button" className="seLink" onClick={() => setShowPaid((was) => !was)} aria-expanded={showPaid}>
              {showPaid ? "Hide" : "Show"} {paid.length} paid
            </button>
            {showPaid && <ul className="seInvoices">{paid.map(row)}</ul>}
          </>
        )}
      </section>

      {year && <CraWatch year={year} />}
      {year && <BusinessExpenses userId={userId} year={year.year} expenses={year.expenses} onChanged={load} />}

      {clients.length > 0 && (
        <section className="seCard" aria-label="Clients">
          <h2 className="seHeading">Clients</h2>
          <ul className="seList">
            {clients.map((c) => (
              <li key={c.id} className="seRow">
                <span className="seRowMain">{c.name}{c.archived && <span className="muted small-text"> (archived)</span>}</span>
                <span className="small-text">
                  {c.invoices} {c.invoices === 1 ? "invoice" : "invoices"}, {formatMoney(c.invoiced, { whole: true })}
                  {c.unpaid > 0 ? `, ${formatMoney(c.unpaid, { whole: true })} unpaid` : ""}
                </span>
                <button type="button" className="seLink"
                  onClick={() => act(() => updateClient(userId, c.id, { archived: !c.archived }))}>
                  {c.archived ? "Unarchive" : "Archive"}
                </button>
                {c.invoices === 0 && (
                  <button type="button" className="seLink" onClick={() => setDeletingClient(c)}
                    aria-label={`Delete client ${c.name}`}>Delete</button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {(composing || editing) && (
        <InvoiceModal userId={userId} invoice={editing} clients={clients} nextNumber={year?.next_number ?? "INV-001"}
          onClose={() => { setComposing(false); setEditing(null); }} onSaved={load} />
      )}
      {paying && (
        <InvoicePaidModal userId={userId} invoice={paying} accounts={accounts}
          onClose={() => setPaying(null)} onSaved={load} />
      )}
      {deleting && (
        <DeleteConfirmModal
          open
          submitting={false}
          title={`Delete invoice ${deleting.number}?`}
          message={deleting.deposited ? "Its payment comes out of your money too." : "This can't be undone."}
          onCancel={() => setDeleting(null)}
          onConfirm={() => { const doomed = deleting; setDeleting(null); act(() => deleteInvoice(userId, doomed.id)); }}
        />
      )}
      {deletingClient && (
        <DeleteConfirmModal
          open
          submitting={false}
          title={`Delete ${deletingClient.name}?`}
          message="They have no invoices, so nothing else goes with them."
          onCancel={() => setDeletingClient(null)}
          onConfirm={() => {
            const doomed = deletingClient;
            setDeletingClient(null);
            act(() => deleteClient(userId, doomed.id));
          }}
        />
      )}
    </div>
  );
}
