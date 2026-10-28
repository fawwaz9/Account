import { useState } from "react";
import ProgressBar from "./ProgressBar";
import { BudgetSummary } from "../types";
import { formatMoney } from "../money";

/** Props for the planned-spend panel. */
interface PlannedSpendProps {
  readonly summary: BudgetSummary | null;
  readonly month: string;
  readonly onMonthChange: (month: string) => void;
  /** Save one account's planned amount for the month. */
  readonly onSetTarget: (accountId: string, planned: number) => Promise<void>;
  /** True while a newly picked month's figures are still loading. */
  readonly pending?: boolean;
}

/**
 * Each account's spending against its planned amount for a month, with a month picker.
 * A plain target is edited in place; one derived from category limits is read-only here.
 */
export default function PlannedSpend({
  summary,
  month,
  onMonthChange,
  onSetTarget,
  pending = false,
}: PlannedSpendProps) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);

  async function commit(accountId: string) {
    setSaving(true);
    try {
      await onSetTarget(accountId, Number(draft || 0));
      setEditing(null);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="plannedSpend" aria-busy={pending}>
      <div className="sectionHeading">
        <h2>Planned spend</h2>
        <input
          className="loginInput monthPicker"
          type="month"
          value={month.slice(0, 7)}
          onChange={(event) => onMonthChange(`${event.target.value}-01`)}
          aria-label="Budget month"
        />
      </div>

      {!summary || summary.accounts.length === 0 ? (
        <p className="muted small-text">No accounts to budget yet.</p>
      ) : (
        <>
          <div className="plannedTotals small-text muted">
            {formatMoney(summary.total_actual)} spent of {formatMoney(summary.total_planned)} planned
          </div>

          <ul className="plannedList">
            {summary.accounts.map((entry) => (
              <li className="plannedRow" key={entry.account_id}>
                <div className="plannedTop">
                  <span className="plannedName">{entry.account_name}</span>

                  {editing === entry.account_id ? (
                    <span className="plannedEdit">
                      <input
                        className="loginInput plannedInput"
                        type="number"
                        min={0}
                        step="0.01"
                        value={draft}
                        autoFocus
                        onChange={(event) => setDraft(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") commit(entry.account_id);
                          if (event.key === "Escape") setEditing(null);
                        }}
                        aria-label={`Planned amount for ${entry.account_name}`}
                      />
                      <button
                        type="button"
                        className="buttons"
                        onClick={() => commit(entry.account_id)}
                        disabled={saving}
                      >
                        Save
                      </button>
                    </span>
                  ) : (() => {
                    const figure = `${formatMoney(entry.actual)} / ${formatMoney(entry.planned)}`;

                    // A derived target is the sum of that account's category
                    // limits, set on its own page. Shown here, but not
                    // editable: one number with two places to set it is the
                    // shape where whichever you edited last quietly wins.
                    if (entry.planned_is_derived) {
                      return (
                        <span
                          className="plannedFigure plannedFigureDerived"
                          title="From this account's category limits — set them on the account's page"
                        >
                          {figure}
                        </span>
                      );
                    }

                    return (
                      <button
                        type="button"
                        className="plannedFigure"
                        onClick={() => {
                          setEditing(entry.account_id);
                          setDraft(String(entry.planned || ""));
                        }}
                      >
                        {figure}
                      </button>
                    );
                  })()}
                </div>

                <ProgressBar
                  value={entry.actual}
                  max={entry.planned}
                  percent={entry.used_percent}
                  label={`${entry.account_name} spend against target`}
                />

                <span className="small-text muted plannedNote">
                  {(() => {
                    if (entry.planned_is_derived) return "Budgeted by category on this account's page";
                    if (entry.planned === 0) return "No target set — click the figure to add one";
                    if (entry.remaining < 0) return `${formatMoney(-entry.remaining)} over`;
                    return `${formatMoney(entry.remaining)} left`;
                  })()}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
