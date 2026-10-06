import { useEffect, useState } from "react";
import { fetchPlanReview, savePlan } from "../api";
import { MonthReview, PlanReview } from "../types";
import { formatMoney } from "../money";

interface PlanVsActualProps {
  readonly userId: string;
  /** Bumped by the page when something changes, to refetch. */
  readonly nonce: number;
}

/**
 * The plan against what happened (Phase 1 D37).
 *
 * The plan above is recomputed on every read, so on its own it can never be
 * wrong. Saving it keeps it as it stands; each finished month is then set
 * against the newest plan saved before that month began. A plan saved mid-month
 * starts with the next one, since its first row only covers the days after it.
 */
export default function PlanVsActual({ userId, nonce }: PlanVsActualProps) {
  const [review, setReview] = useState<PlanReview | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedNonce, setSavedNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchPlanReview(userId)
      .then((result) => { if (!cancelled) setReview(result); })
      .catch(() => { if (!cancelled) setReview(null); });
    return () => { cancelled = true; };
  }, [userId, nonce, savedNonce]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await savePlan(userId);
      setSavedNonce((n) => n + 1);
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Couldn't save the plan.");
    } finally {
      setSaving(false);
    }
  }

  const latest = review?.latest ?? null;
  const months = review?.months ?? [];

  return (
    <div className="planVsActual">
      <div className="planVsActualHead">
        <button type="button" className="buttons" onClick={() => void save()} disabled={saving}>
          {saving ? "Saving…" : "Save as my plan"}
        </button>
        <span className="small-text muted" role="status">
          {latest
            ? `Saved ${longDate(latest.saved_on)}. Each month from ${monthName(nextMonth(latest.saved_on))} is compared with it.`
            : "Save the plan to see, month by month, how it held up."}
        </span>
      </div>
      {error && <p className="small-text error" role="alert">{error}</p>}

      {months.length > 0 && (
        <div className="yearPlanTable">
          <table aria-label="The plan against what happened">
            <thead>
              <tr>
                <th scope="col">Month</th>
                <th scope="col">In</th>
                <th scope="col">Out</th>
                <th scope="col">Balance</th>
              </tr>
            </thead>
            <tbody>
              {months.map((row) => <ReviewRow key={row.month} row={row} />)}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/** What happened, large; what the plan said, small beneath it. */
function ReviewRow({ row }: { readonly row: MonthReview }) {
  const overspent = row.actual_out > row.planned_out;
  const behind = row.actual_end < row.planned_end;
  return (
    <tr>
      <th scope="row">
        {monthName(row.month)}
        {row.tuition_out > 0 && (
          <span className="small-text muted planVsActualNote">
            includes {formatMoney(row.tuition_out)} tuition, which the plan leaves out
          </span>
        )}
      </th>
      <Cell actual={row.actual_in} planned={row.planned_in} />
      <Cell actual={row.actual_out} planned={row.planned_out} worse={overspent} />
      <Cell actual={row.actual_end} planned={row.planned_end} worse={behind} />
    </tr>
  );
}

function Cell({ actual, planned, worse = false }: { readonly actual: number; readonly planned: number; readonly worse?: boolean }) {
  return (
    <td>
      <span className={worse ? "yearPlanNegative" : undefined}>{formatMoney(actual)}</span>
      <span className="small-text muted planVsActualPlanned">plan {formatMoney(planned)}</span>
    </td>
  );
}

/** The first of the following month, from the date string itself: going via
 * toISOString would convert to UTC and, east of Greenwich, land a day early. */
function nextMonth(value: string): string {
  const [year, month] = value.split("-").map(Number);
  return month === 12 ? `${year + 1}-01-01` : `${year}-${String(month + 1).padStart(2, "0")}-01`;
}

function monthName(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { month: "short", year: "numeric" });
}

function longDate(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
    month: "short", day: "numeric", year: "numeric",
  });
}
