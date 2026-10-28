import { ShiftOccurrence } from "../types";
import { Link } from "react-router-dom";
import { clockTime, dueLabel, today } from "../../../shared/utils/dateUtils";
import { arrangeShifts } from "../shiftOrder";
import HelpTip from "../../../shared/components/HelpTip";

/** Props for the shift list. */
interface ShiftListProps {
  readonly shifts: ShiftOccurrence[];
  readonly onConfirm: (shift: ShiftOccurrence) => void;
  /** Ask to remove a one-off shift; the page confirms first. */
  readonly onRemove: (shift: ShiftOccurrence) => void;
  readonly busy: boolean;
}

/**
 * Shifts around today, unconfirmed past ones first, each confirmable; one-offs removable.
 * An unconfirmed past shift shows its scheduled hours, marked as assumed rather than hidden.
 */
export default function ShiftList({ shifts, onConfirm, onRemove, busy }: ShiftListProps) {
  const shown = arrangeShifts(shifts, today());
  if (shown.length === 0) {
    return <p className="calMuted">No shifts scheduled. Set a pattern on a job to fill this in.</p>;
  }

  const needing = shifts.filter((shift) => shift.assumed).length;

  return (
    <section className="shiftSection">
      <div className="sectionHeading">
        <h2>Shifts</h2>
        <span className="small-text muted">
          {needing > 0
            ? `${needing} ${needing === 1 ? "shift needs" : "shifts need"} confirming`
            : "All confirmed"}
        </span>
      </div>

      <ul className="shiftList">
        {shown.map((shift) => (
          <li
            key={`${shift.event_id}-${shift.on_date}`}
            className={`shiftRow${shift.assumed ? " shiftRowAssumed" : ""}`}
          >
            <span className="shiftWhen">{dueLabel(shift.on_date)}</span>

            <span className="shiftBody">
              <span className="shiftJob">{shift.job_name}</span>
              <span className="small-text muted">
                {[
                  clockTime(shift.scheduled_start),
                  clockTime(shift.scheduled_end),
                ].filter(Boolean).join("–")}
                {shift.location ? ` · ${shift.location}` : ""}
              </span>
            </span>

            <span className="shiftHours">
              {hours(shift.counted_minutes)}
              {shift.counted_minutes !== shift.scheduled_minutes && (
                <span className="small-text muted"> of {hours(shift.scheduled_minutes)}</span>
              )}
            </span>

            {shift.confirmed ? (
              <span className="shiftState shiftStateDone">
                Confirmed
                {/* A cash tip waiting for somewhere to go: recorded, but not in
                    the budget until an account is chosen for cash tips. A tip on
                    the cheque is never "waiting" -- it arrives with the pay. */}
                {heldTip(shift) && (
                  <HelpTip label="This tip is not in your budget" tone="warning">
                    Cash tips wait until you choose an account for them.{" "}
                    <Link to="/settings?tab=financial">Choose in Settings</Link>
                  </HelpTip>
                )}
              </span>
            ) : (
              <button
                type="button"
                className="shiftConfirm"
                onClick={() => onConfirm(shift)}
                disabled={busy}
              >
                {shift.assumed ? "Confirm" : "Log"}
              </button>
            )}

            {/* Only a shift entered on its own has a row to remove. A pattern
                date is cancelled on the calendar instead -- it has none. */}
            {!shift.repeats && (
              <button
                type="button"
                className="shiftRemove"
                onClick={() => onRemove(shift)}
                disabled={busy}
                aria-label={`Remove the ${shift.job_name} shift on ${shift.on_date}`}
                title={
                  shift.confirmed
                    ? "Remove this shift, including anything already confirmed"
                    : "Remove this shift"
                }
              >
                Remove
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Minutes as hours to one decimal, e.g. "7.5h". */
function hours(minutes: number): string {
  return `${Math.round((minutes / 60) * 10) / 10}h`;
}

/** A confirmed cash tip that has not reached the budget yet. */
export function heldTip(shift: ShiftOccurrence): boolean {
  return shift.confirmed && shift.tip_is_cash && shift.tip_amount > 0 && !shift.tip_in_ledger;
}

