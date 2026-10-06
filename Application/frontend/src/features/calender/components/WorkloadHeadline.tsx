import { duration } from "../../../shared/utils/dateUtils";
import { WorkloadForecast } from "../hooks/useWorkloadForecast";

/**
 * "14h of estimated work in the next 7 days, 9h free" -- Phase 1 item 3.
 *
 * Says nothing when nothing is due: a line reporting an empty week is a line
 * that only states an absence. When some tasks carry no estimate it says how
 * many, because then the figure is a floor, and that changes what you do with
 * it.
 */
export default function WorkloadHeadline({ forecast }: { readonly forecast: WorkloadForecast }) {
  const { estimatedMinutes, taskCount, unestimatedTasks, freeMinutes } = forecast;
  if (taskCount === 0) return null;

  const tasks = `${taskCount} ${taskCount === 1 ? "task" : "tasks"}`;
  const free = <strong>{duration(freeMinutes) || "0h"}</strong>;

  if (estimatedMinutes === 0) {
    return (
      <p className="workloadHeadline">
        Next 7 days: {tasks} due, none with an estimate. {free} free in your study hours.
      </p>
    );
  }

  const over = estimatedMinutes > freeMinutes;
  return (
    <div className="workloadHeadline">
      <p>
        Next 7 days: <strong>{duration(estimatedMinutes)}</strong> of estimated work, {free} free
        in your study hours.
        {over && <span className="workloadOver"> More work than free time.</span>}
      </p>
      {/* Said whenever it applies: the figure is not what was typed, and a
          number that changed without saying so is one nobody can check. */}
      {forecast.estimateRatio != null && (
        <p className="workloadCaveat">
          Your estimates ({duration(forecast.typedMinutes ?? 0) || "0h"}) × {forecast.estimateRatio.toFixed(2)}, how long
          tasks have really been taking. Turn it off on Tasks.
        </p>
      )}
      {unestimatedTasks > 0 && (
        <p className="workloadCaveat">
          {unestimatedTasks} of {tasks} {unestimatedTasks === 1 ? "has" : "have"} no estimate, so
          the real figure is higher.
        </p>
      )}
    </div>
  );
}
