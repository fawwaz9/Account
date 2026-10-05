import { useEffect, useState } from "react";
import { PayCheck, Paycheque } from "../types";
import { formatMoney } from "../../budget/money";
import { dueLabel } from "../../../shared/utils/dateUtils";
import { checkPaycheque } from "../api";
import { useAuth } from "../../../app/auth/AuthContext";
import PayCheckPanel from "./PayCheckPanel";

interface PaychequeListProps {
  readonly paycheques: Paycheque[];
  readonly onEdit: (paycheque: Paycheque) => void;
  readonly onAdd: () => void;
  readonly busy: boolean;
}

/**
 * The cheques that have arrived.
 *
 * Gross and net both shown, because the gap between them is the thing this
 * page can answer and the ledger cannot: the ledger only ever saw the net.
 */
export default function PaychequeList({
  paycheques,
  onEdit,
  onAdd,
  busy,
}: PaychequeListProps) {
  const { user } = useAuth();
  const [open, setOpen] = useState<string | null>(null);
  const [checks, setChecks] = useState<Record<string, PayCheck>>({});
  const [checking, setChecking] = useState<string | null>(null);
  const [checkError, setCheckError] = useState<{ id: string; message: string } | null>(null);

  // A new list means a cheque or its shifts may have changed: a cached check
  // would describe a cheque that no longer exists in that form.
  useEffect(() => {
    setChecks({});
  }, [paycheques]);

  // Asked for on press, never in the background: it recomputes from the shifts
  // as they are now, which is a different question from the verdict stored
  // when the cheque was recorded, so it should only appear when asked.
  async function toggleCheck(cheque: Paycheque) {
    if (open === cheque.id) {
      setOpen(null);
      return;
    }
    setOpen(cheque.id);
    setCheckError(null);
    if (checks[cheque.id] || !user) return;
    setChecking(cheque.id);
    try {
      const result = await checkPaycheque(user.id, cheque.id);
      setChecks((previous) => ({ ...previous, [cheque.id]: result }));
    } catch {
      setCheckError({ id: cheque.id, message: "Couldn't check this cheque. Try again in a moment." });
    } finally {
      setChecking(null);
    }
  }

  return (
    <section className="paySection">
      <div className="sectionHeading">
        <h2>Paycheques</h2>
        <button type="button" className="calButton" onClick={onAdd} disabled={busy}>
          Record one
        </button>
      </div>

      {paycheques.length === 0 ? (
        <p className="calMuted">
          No cheques recorded. Recording one puts the net in your budget and keeps
          the gross and deductions here.
        </p>
      ) : (
        <ul className="payList">
          {paycheques.map((cheque) => (
            <li key={cheque.id} className="payRow">
              <span className="payWhen">{dueLabel(cheque.occurred_on)}</span>

              <span className="payBody">
                <span className="payJob">{cheque.job_name}</span>
                <span className="small-text muted">
                  {formatMoney(cheque.gross_amount)} gross
                  {cheque.deductions.length > 0 &&
                    ` · ${formatMoney(deducted(cheque))} deducted`}
                </span>
              </span>

              <span className="payNetCell">{formatMoney(cheque.net_amount)}</span>

              <span className={varianceClass(cheque)}>{varianceLabel(cheque)}</span>

              <span className="payActions">
                <button
                  type="button"
                  className="jobButton"
                  onClick={() => toggleCheck(cheque)}
                  disabled={checking === cheque.id}
                  aria-expanded={open === cheque.id}
                  aria-label={`Check the math on the cheque from ${cheque.occurred_on}`}
                >
                  {checking === cheque.id ? "Checking…" : open === cheque.id ? "Hide the math" : "Check the math"}
                </button>
                <button
                  type="button"
                  className="jobButton"
                  onClick={() => onEdit(cheque)}
                  disabled={busy}
                  aria-label={`Edit the cheque from ${cheque.occurred_on}`}
                >
                  Edit
                </button>
              </span>

              {open === cheque.id && checks[cheque.id] && <PayCheckPanel check={checks[cheque.id]} />}
              {open === cheque.id && checkError?.id === cheque.id && (
                <p className="small-text error payCheck" role="alert">{checkError.message}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function deducted(cheque: Paycheque): number {
  return cheque.deductions.reduce((total, entry) => total + entry.amount, 0);
}

/** Only a short cheque is worth colouring; matching or over is not a problem. */
function varianceClass(cheque: Paycheque): string {
  if (cheque.variance === null) return "payVariance";
  return cheque.variance < -0.01 ? "payVariance payVarianceShort" : "payVariance";
}

function varianceLabel(cheque: Paycheque): string {
  if (cheque.variance === null) return "";
  if (cheque.variance < -0.01) return `${formatMoney(-cheque.variance)} short`;
  if (cheque.variance > 0.01) return `${formatMoney(cheque.variance)} over`;
  return "As expected";
}
