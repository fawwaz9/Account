import { useEffect, useState } from "react";
import {
  contributeToFund,
  deleteSinkingFund,
  fetchSinkingFunds,
  undoContribution,
} from "../api";
import DeleteConfirmModal from "../../grades/components/DeleteConfirmModal";
import { SinkingFund } from "../types";
import HelpTip from "../../../shared/components/HelpTip";
import { formatMoney } from "../money";
import { useAuth } from "../../../app/auth/AuthContext";
import { dueLabel } from "../../../shared/utils/dateUtils";

/** Props for the sinking funds panel. */
interface SinkingFundsProps {
  /** Bumped by the page when something changes, to refetch. */
  readonly nonce: number;
  /** Open the new-fund dialog. */
  readonly onAdd: () => void;
  /** Called after any change, so the page reloads. */
  readonly onChanged: () => void;
}

/**
 * Sinking funds with progress, this month's contribution, undo and removal.
 * Setting aside writes a real transfer; removing a fund deletes its transfers, after a confirm.
 */
export default function SinkingFunds({ nonce, onAdd, onChanged }: SinkingFundsProps) {
  const { user } = useAuth();
  const [funds, setFunds] = useState<SinkingFund[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Removing a fund takes its transfers with it, so it asks first. The modal
  // rather than the inline "Yes / Keep" pair used elsewhere in an editable list:
  // the cascade needs a sentence, and the inline pair has nowhere to put one.
  const [pendingRemoval, setPendingRemoval] = useState<SinkingFund | null>(null);

  useEffect(() => {
    if (!user) return;

    let cancelled = false;
    fetchSinkingFunds(user.id)
      .then((rows) => { if (!cancelled) setFunds(rows); })
      .catch(() => { if (!cancelled) setFunds([]); });

    return () => { cancelled = true; };
  }, [user, nonce]);

  async function act(action: () => Promise<unknown>, failure: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : failure);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="sinkSection">
      <div className="sectionHeading">
        <h2>Set aside</h2>
        <HelpTip label="What setting aside does">
          A fund says what something costs and when it is due, and works out what to
          put by each month. A missed month raises the rest rather than quietly moving
          the deadline.
        </HelpTip>
        <button type="button" className="calButton" onClick={onAdd} disabled={busy}>
          New fund
        </button>
      </div>

      {error && <p className="calError">{error}</p>}

      {funds.length === 0 ? (
        <p className="muted small-text">Nothing reserved yet.</p>
      ) : (
        <ul className="sinkList">
          {funds.map((fund) => (
            <li key={fund.id} className={`sinkCard${fund.overdue ? " sinkCardOverdue" : ""}`}>
              <div className="sinkHead">
                <span className="sinkName">{fund.name}</span>
                <span className="small-text muted">
                  {formatMoney(fund.target_amount)} by {dueLabel(fund.due_on)}
                </span>
              </div>

              <div className="sinkBar" role="img"
                   aria-label={`${formatMoney(fund.saved)} of ${formatMoney(fund.target_amount)} set aside`}>
                <span
                  className="sinkBarFill"
                  style={{ width: `${percent(fund.saved, fund.target_amount)}%` }}
                />
              </div>

              <span className="small-text muted">
                {formatMoney(fund.saved)} set aside · {formatMoney(fund.remaining)} to go
                {fund.months_left > 0 && ` · ${fund.months_left} ${fund.months_left === 1 ? "month" : "months"} left`}
              </span>

              {fund.remaining === 0 ? (
                <span className="sinkDone small-text">Fully funded</span>
              ) : fund.funded_this_month ? (
                <div className="sinkActions">
                  <span className="sinkDone small-text">This month is set aside</span>
                  <button
                    type="button"
                    className="sinkUndo"
                    disabled={busy}
                    onClick={() => act(
                      () => undoContribution(user!.id, fund.id, latest(fund)!.id),
                      "Could not undo that"
                    )}
                  >
                    Undo
                  </button>
                </div>
              ) : (
                <div className="sinkActions">
                  <button
                    type="button"
                    className="sinkPut"
                    disabled={busy}
                    onClick={() => act(
                      () => contributeToFund(user!.id, fund.id, { amount: null, occurred_on: null }),
                      "Could not set that aside"
                    )}
                  >
                    Set aside {formatMoney(fund.per_month)}
                  </button>
                  {fund.overdue && (
                    <span className="small-text sinkOverdueNote">
                      Past its date — this is the whole remainder
                    </span>
                  )}
                </div>
              )}

              <button
                type="button"
                className="sinkRemove small-text"
                disabled={busy}
                onClick={() => setPendingRemoval(fund)}
                aria-label={`Remove ${fund.name} and its transfers`}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      {/* It announced the cascade in its own aria-label and then performed it on
          one click. Now the label is a promise the dialog keeps. */}
      <DeleteConfirmModal
        open={pendingRemoval !== null}
        title="Remove this fund?"
        message={
          pendingRemoval
            ? `"${pendingRemoval.name}" and every transfer recorded against it will ` +
              `be removed. The money itself stays in the account it was moved to; ` +
              `what goes is the goal and its history.`
            : ""
        }
        confirmLabel="Remove the fund"
        submitting={busy}
        error={error}
        onCancel={() => setPendingRemoval(null)}
        onConfirm={async () => {
          const fund = pendingRemoval;
          if (!fund) return;
          await act(() => deleteSinkingFund(user!.id, fund.id), "Could not remove that fund");
          setPendingRemoval(null);
        }}
      />
    </section>
  );
}

/** Part of whole as a percent, capped at 100; 0 with no target. */
function percent(part: number, whole: number): number {
  return whole <= 0 ? 0 : Math.min(100, (part / whole) * 100);
}

/** The most recent contribution, which Undo takes back. */
function latest(fund: SinkingFund) {
  return fund.contributions[fund.contributions.length - 1];
}
