import { useEffect, useId, useState } from "react";
import DeleteConfirmModal from "../../grades/components/DeleteConfirmModal";
import HelpTip from "../../../shared/components/HelpTip";
import { clearAccountMonthValue, setAccountMonthValue } from "../api";
import { formatMoney, formatPercent } from "../money";
import { monthLabel } from "../../../shared/utils/dateUtils";
import { InvestmentReturn } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";

/** Props for the investment reading panel. */
interface InvestmentReturnPanelProps {
  readonly accountId: string;
  /** Month on screen, YYYY-MM-01; the reading is recorded against it. */
  readonly month: string;
  /** Reading that applies to that month, carried forward or not. */
  readonly figure: InvestmentReturn | null;
  /** Ledger balance at that month's end; the typed value is measured against it. */
  readonly ledgerAtMonth: number;
  readonly onSaved: () => void | Promise<void>;
}

/**
 * Record what an investment is worth for the month shown; the app works out the gain.
 * A carried-forward reading never pre-fills the field, so saving cannot re-record an old figure.
 */
export default function InvestmentReturnPanel({
  accountId,
  month,
  figure,
  ledgerAtMonth,
  onSaved,
}: InvestmentReturnPanelProps) {
  const { user } = useAuth();
  const fieldId = useId();

  // A reading carried forward from an earlier month is not this month's answer,
  // so its typed value must not pre-fill this month's field -- saving without
  // touching it would otherwise silently re-record an old figure as current.
  const recorded = figure && !figure.is_carried_forward ? figure : null;
  const seed = recorded?.market_value != null ? String(recorded.market_value) : "";

  const [draft, setDraft] = useState(seed);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingClear, setConfirmingClear] = useState(false);

  // Keyed on the seed rather than on the figure object, so a reload that changes
  // nothing cannot wipe out something half-typed. Switching months reseeds,
  // which is the case this exists for.
  useEffect(() => {
    setDraft(seed);
    setError(null);
  }, [month, seed]);

  const typed = Number(draft);
  const entered = draft.trim() !== "" && Number.isFinite(typed);

  // A preview of a number the server has not seen yet, which is the one case
  // where computing a percentage in the client is right rather than a second
  // opinion on a stored one. It rounds the way the display does, so the figure
  // does not move when it comes back saved.
  const previewDifference = entered ? typed - ledgerAtMonth : null;
  const previewPercent =
    previewDifference !== null && ledgerAtMonth > 0
      ? (previewDifference / ledgerAtMonth) * 100
      : null;

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!user || !entered || saving) return;

    setSaving(true);
    setError(null);
    try {
      await setAccountMonthValue(user.id, accountId, month, typed);
      await onSaved();
    } catch {
      setError("That did not save. Try again.");
    } finally {
      setSaving(false);
    }
  }

  async function clear() {
    if (!user) return;
    setSaving(true);
    setError(null);
    try {
      await clearAccountMonthValue(user.id, accountId, month);
      setConfirmingClear(false);
      await onSaved();
    } catch {
      setError("That did not clear. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="accountReturn">
      <div className="sectionHeading">
        <h2>What it is worth</h2>
        <HelpTip label="What this figure means">
          Your balance is the sum of what you have paid in, so it cannot tell you
          whether the holding has grown. Type what the investment is worth today
          and the difference between the two is your return. Record it once a
          month; a month you skip keeps the last figure, dated.
        </HelpTip>
      </div>

      {figure ? (
        <p className="accountReturnFigure">
          <span
            className={
              figure.difference_amount < 0
                ? "accountReturnAmount accountReturnAmount--down"
                : "accountReturnAmount"
            }
          >
            {formatMoney(figure.difference_amount, { signed: true })}
          </span>
          {figure.return_percent != null && (
            <span className="accountReturnPercent">
              {formatPercent(figure.return_percent, { signed: true })}
            </span>
          )}
          <span className="small-text muted accountReturnNote">
            {figure.difference_amount < 0 ? "below" : "above"} the{" "}
            {formatMoney(figure.ledger_balance)} you put in
            {figure.is_carried_forward
              ? ` · carried forward from ${monthLabel(figure.as_of)}`
              : ` · recorded for ${monthLabel(figure.as_of)}`}
          </span>
        </p>
      ) : (
        <p className="small-text muted accountReturnNote">
          Nothing recorded for this month or any before it. Type what the holding
          is worth to see your return.
        </p>
      )}

      <form className="accountReturnForm" onSubmit={save}>
        <label className="small-text muted" htmlFor={fieldId}>
          What is it worth today?
        </label>
        <div className="accountReturnRow">
          <input
            id={fieldId}
            className="loginInput accountReturnInput"
            type="number"
            step="0.01"
            inputMode="decimal"
            placeholder={String(ledgerAtMonth)}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
          <button type="submit" className="buttons addCourseButton" disabled={!entered || saving}>
            {saving ? "Saving..." : "Save"}
          </button>
          {/* Only offered for a reading this month actually holds. Clearing a
              month that is only showing an earlier figure would delete that
              earlier month's reading from a screen that never named it. */}
          {recorded && (
            <button
              type="button"
              className="accountReturnClear"
              onClick={() => setConfirmingClear(true)}
              disabled={saving}
            >
              Clear this month
            </button>
          )}
        </div>

        {previewDifference !== null && (
          <p className="small-text accountReturnPreview" aria-live="polite">
            {formatMoney(ledgerAtMonth)} paid in &rarr;{" "}
            {previewDifference < 0 ? "down" : "up"}{" "}
            {formatMoney(Math.abs(previewDifference))}
            {previewPercent !== null && ` (${formatPercent(previewPercent, { signed: true })})`}
          </p>
        )}

        {error && <p className="small-text accountReturnError">{error}</p>}
      </form>

      <DeleteConfirmModal
        open={confirmingClear}
        title="Clear this month's figure?"
        message={
          `The reading recorded for ${monthLabel(month)} will be removed. Earlier ` +
          `months keep theirs, and this month will show the last figure before it.`
        }
        confirmLabel="Clear it"
        onConfirm={clear}
        onCancel={() => setConfirmingClear(false)}
        submitting={saving}
        error={error}
      />
    </section>
  );
}
