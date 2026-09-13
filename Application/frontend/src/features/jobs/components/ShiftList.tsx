import { ShiftOccurrence } from "../types";
import { clockTime, dueLabel } from "../../../shared/utils/dateUtils";

interface ShiftListProps {
  readonly shifts: ShiftOccurrence[];
  readonly onConfirm: (shift: ShiftOccurrence) => void;
  readonly busy: boolean;
}

/**
 * The shifts around today, with the ones still needing confirming called out.
 *
 * An unconfirmed past shift is shown with its scheduled hours and marked, not
 * hidden: forgetting the admin is not the same as not having worked, and a
 * fortnight of assumed hours should look like a fortnight of work with a
 * question over it.
 */
export default function ShiftList({ shifts, onConfirm, busy }: ShiftListProps) {
  if (shifts.length === 0) {
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
        {shifts.map((shift) => (
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
              <span className="shiftState shiftStateDone">Confirmed</span>
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
          </li>
        ))}
      </ul>
    </section>
  );
}

function hours(minutes: number): string {
  return `${Math.round((minutes / 60) * 10) / 10}h`;
}
