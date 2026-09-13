import { Paycheque } from "../types";
import { formatMoney } from "../../budget/money";
import { dueLabel } from "../../../shared/utils/dateUtils";

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

              <button
                type="button"
                className="jobButton"
                onClick={() => onEdit(cheque)}
                disabled={busy}
                aria-label={`Edit the cheque from ${cheque.occurred_on}`}
              >
                Edit
              </button>
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
