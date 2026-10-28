import { SafeToSpend as Safe } from "../types";
import { formatMoney } from "../money";
import { dueLabel } from "../../../shared/utils/dateUtils";

/** Props: the server's safe-to-spend, or null while loading. */
interface SafeToSpendProps {
  readonly safe: Safe | null;
}

/**
 * Safe-to-spend headline until the next payday, with its workings beneath.
 * `safe_soon`, counting unpaid work, is context and never the headline.
 */
export default function SafeToSpend({ safe }: SafeToSpendProps) {
  if (!safe) return null;

  const over = safe.safe_now < 0;

  return (
    <section className={`safeBlock${over ? " safeBlockOver" : ""}`} aria-label="Safe to spend">
      <div className="safeHead">
        <span className="small-text muted safeLabel">
          {over ? "Over-committed" : "Safe to spend"}
        </span>
        <span className="small-text muted">
          {/* The window is half the answer. "$1,228" is a number; "$1,228 until
              23 Oct" is something you can act on. */}
          until {dueLabel(safe.ends_on)}
          {safe.until_payday ? ", your next cheque" : ", the end of the month"}
          {" · "}{safe.days} {safe.days === 1 ? "day" : "days"}
        </span>
      </div>

      <span className="safeHeadline">{formatMoney(safe.safe_now)}</span>

      {safe.per_day !== null && (
        <span className="small-text muted">{formatMoney(safe.per_day)} a day</span>
      )}

      <ul className="safeParts">
        <li>
          <span>In your spending accounts</span>
          <span>{formatMoney(safe.spendable)}</span>
        </li>
        {safe.committed > 0 && (
          <li>
            <span>Already committed</span>
            <span className="safeMinus">−{formatMoney(safe.committed)}</span>
          </li>
        )}
        {safe.earmarked > 0 && (
          <li>
            <span>Set aside, not yet moved</span>
            <span className="safeMinus">−{formatMoney(safe.earmarked)}</span>
          </li>
        )}
      </ul>

      {/* Context, never the headline: it is money a late or short cheque might
          not bring, and acting on it is how an overdraft happens. */}
      {safe.owed_to_you > 0 && (
        <p className="small-text muted safeSoon">
          {formatMoney(safe.safe_soon)} counting {formatMoney(safe.owed_to_you)} of
          work you have done but not been paid for.
        </p>
      )}

      {safe.commitments.length > 0 && (
        <details className="safeCommitments">
          <summary className="small-text muted">
            {safe.commitments.length}{" "}
            {safe.commitments.length === 1 ? "charge" : "charges"} before then
          </summary>
          <ul>
            {safe.commitments.map((charge, at) => (
              <li key={`${charge.on_date}-${at}`}>
                <span className="small-text">{charge.description ?? "Payment"}</span>
                <span className="small-text muted">
                  {dueLabel(charge.on_date)} · {formatMoney(charge.amount)}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
