import { DeadlineRisk } from "../types";
import { duration, dueLabel } from "../../../shared/utils/dateUtils";
import HelpTip from "../../../shared/components/HelpTip";

/** The reading, or null while it loads or when it failed. */
interface DeadlineRiskCardProps {
  readonly risk: DeadlineRisk | null;
}

/** Minutes as "1h 5m", rounding to the minute; "0m" rather than "" for nothing. */
function minutes(value: number): string {
  return duration(Math.round(value)) || "0m";
}

/**
 * Deadline risk (Phase 4 item 3): your usual pace against what each due date needs.
 * Quiet until there is enough history, and says how close it is; then names only the
 * deadlines at risk, with the two rates and the shortfall.
 */
export default function DeadlineRiskCard({ risk }: DeadlineRiskCardProps) {
  if (!risk) return null;

  if (!risk.ready) {
    // Nothing finished with a time yet: nothing to say, not even "waiting".
    if (risk.counted_tasks === 0) return null;
    return (
      <section className="deadlineRisk deadlineRiskQuiet" aria-label="Deadline risk">
        <p className="small-text muted">
          Deadline risk starts once it knows your pace: {Math.min(risk.history_days, risk.needed_days)} of{" "}
          {risk.needed_days} days, {Math.min(risk.counted_tasks, risk.needed_tasks)} of {risk.needed_tasks} finished
          tasks with a time.
        </p>
      </section>
    );
  }

  const pace = risk.velocity_minutes_per_day ?? 0;
  const atRisk = risk.deadlines.filter((d) => d.at_risk);

  return (
    <section className="deadlineRisk" aria-label="Deadline risk">
      <div className="labelWithTip">
        <h2 className="taskGroupTitle deadlineRiskTitle">
          {atRisk.length === 0 ? "On pace" : `${atRisk.length} deadline${atRisk.length === 1 ? "" : "s"} at risk`}
        </h2>
        <HelpTip label="How deadline risk is worked out">
          Your pace is the time you finished per day over the last {risk.window_days} days: each task's
          timed or reported minutes, else its estimate. A deadline is at risk when the estimated time
          left on everything due by then, overdue work included, needs more per day than that.
          {risk.estimate_ratio !== null && ` Estimates are scaled by ${risk.estimate_ratio}×, as you asked.`}
        </HelpTip>
      </div>

      <p className="small-text">
        You usually finish about {minutes(pace)} a day.
        {atRisk.length === 0 && ` Everything due in the next ${risk.horizon_days} days fits at that pace.`}
      </p>

      {atRisk.length > 0 && (
        <ul className="deadlineRiskList">
          {atRisk.map((d) => (
            <li key={d.due_date}>
              <span className="deadlineRiskWhen">{dueLabel(d.due_date)}</span>
              <span className="deadlineRiskWhat">
                {d.titles.join(", ")}
                {d.tasks > d.titles.length && ` and ${d.tasks - d.titles.length} more`}
                {d.minutes_by_then > d.own_minutes && (
                  <span className="muted">, with what's due before it</span>
                )}
              </span>
              <span className="small-text muted deadlineRiskWhy">
                needs {minutes(d.required_minutes_per_day)} a day for {d.days_left} day{d.days_left === 1 ? "" : "s"};
                about {minutes(d.shortfall_minutes)} short
              </span>
            </li>
          ))}
        </ul>
      )}

      {risk.unestimated_open > 0 && (
        <p className="small-text muted">
          {risk.unestimated_open} task{risk.unestimated_open === 1 ? " has" : "s have"} no estimate, so{" "}
          {risk.unestimated_open === 1 ? "it isn't" : "they aren't"} counted.
        </p>
      )}
    </section>
  );
}
