import { useEffect, useState } from "react";
import { fetchTransactions, updateTransaction } from "../../budget/api";
import { Transaction } from "../../budget/types";
import { formatMoney } from "../../budget/money";
import { getErrorMessage } from "../../grades/components/AddCourseModal";
import { addDays, shortDate, today } from "../../../shared/utils/dateUtils";
import { BusinessExpense } from "../types";

/** How far back the expenses offered for tagging go. */
const OFFER_DAYS = 90;

/** Props for the business-expenses panel. */
interface Props {
  readonly userId: string;
  readonly year: number;
  readonly expenses: readonly BusinessExpense[];
  readonly onChanged: () => void;
}

/**
 * The year's expenses tagged as business, with the share, and a way to tag a recent one:
 * a phone used half for work is 50%.
 */
export default function BusinessExpenses({ userId, year, expenses, onChanged }: Props) {
  const [recent, setRecent] = useState<Transaction[]>([]);
  const [picked, setPicked] = useState("");
  const [percent, setPercent] = useState("100");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchTransactions(userId, { start: addDays(today(), -OFFER_DAYS), end: today() })
      .then((rows) => { if (!cancelled) setRecent(rows.filter((r) => r.kind === "expense" && !r.business_percent)); })
      .catch(() => { if (!cancelled) setRecent([]); });
    return () => { cancelled = true; };
  }, [userId, expenses]);

  async function tag(transactionId: string, share: number | null) {
    setError(null);
    try {
      await updateTransaction(userId, transactionId, { business_percent: share });
      setPicked("");
      onChanged();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  const total = expenses.reduce((sum, e) => sum + e.business_amount, 0);

  return (
    <section className="seCard" aria-label="Business expenses">
      <h2 className="seHeading">Business expenses, {year}</h2>
      {expenses.length === 0 ? (
        <p className="small-text muted">None tagged yet. Supplies, a share of your phone, software: tag them below.</p>
      ) : (
        <ul className="seList">
          {expenses.map((e) => (
            <li key={e.transaction_id} className="seRow">
              <span className="seRowMain">
                {e.description || "Expense"} <span className="muted small-text">{shortDate(e.occurred_on)}</span>
              </span>
              <span className="small-text">{e.percent}% of {formatMoney(e.amount)}</span>
              <strong>{formatMoney(e.business_amount)}</strong>
              <button type="button" className="seLink" onClick={() => tag(e.transaction_id, null)}
                aria-label={`Untag ${e.description || "expense"}`}>Untag</button>
            </li>
          ))}
          <li className="seRow seTotal"><span className="seRowMain">Total</span><strong>{formatMoney(total)}</strong></li>
        </ul>
      )}
      <form className="seTagForm" onSubmit={(event) => { event.preventDefault(); if (picked) tag(picked, Number(percent)); }}>
        <label className="calField seTagPick">
          <span className="calFieldLabel">Tag a recent expense</span>
          <select className="calInput" value={picked} onChange={(event) => setPicked(event.target.value)}>
            <option value="">Choose one...</option>
            {recent.map((r) => (
              <option key={r.id} value={r.id}>
                {shortDate(r.occurred_on)} · {r.description || "Expense"} · {formatMoney(r.amount)}
              </option>
            ))}
          </select>
        </label>
        <label className="calField seTagPercent">
          <span className="calFieldLabel">Business share %</span>
          <input className="calInput" type="number" min={1} max={100} step={1} required value={percent}
            onChange={(event) => setPercent(event.target.value)} />
        </label>
        <button type="submit" className="calButton" disabled={!picked}>Tag</button>
      </form>
      {error && <p className="loginError">{error}</p>}
    </section>
  );
}
