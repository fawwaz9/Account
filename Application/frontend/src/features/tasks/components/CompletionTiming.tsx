import { CompletionTiming as Timing, TimingWindow } from "../types";

interface CompletionTimingProps {
  readonly timing: Timing | null;
}

/**
 * Whether work is actually getting done on time.
 *
 * Two readings per window, because each hides what the other shows. The signed
 * mean carries magnitude but lets a fortnight late cancel against a fortnight
 * early; the on-time share cannot be skewed by one forgotten task but counts a
 * day late and a month late the same. Shown together, the pair is honest.
 *
 * The early/late split sits under the mean for the same reason: "0.0 days" can
 * mean a punctual fortnight or two weeks of chaos averaging out, and only the
 * split tells you which.
 */
export default function CompletionTiming({ timing }: CompletionTimingProps) {
  // Nothing finished with a date on it yet, so every figure would be blank.
  if (!timing || (timing.past_week.counted === 0 && timing.this_month.counted === 0)) {
    return null;
  }

  return (
    <section className="timingBlock" aria-label="How early or late work gets finished">
      <div className="timingWindows">
        <Window window={timing.past_week} />
        <Window window={timing.this_month} />
      </div>

      {timing.undated_completed > 0 && (
        <p className="small-text muted timingNote">
          {timing.undated_completed} completed{" "}
          {timing.undated_completed === 1 ? "task has" : "tasks have"} no due date
          and {timing.undated_completed === 1 ? "is" : "are"} not counted here.
        </p>
      )}
    </section>
  );
}

function Window({ window }: { readonly window: TimingWindow }) {
  return (
    <div className="timingWindow">
      <span className="small-text muted timingLabel">{window.label}</span>

      {window.counted === 0 ? (
        <span className="timingHeadline timingHeadlineEmpty">Nothing finished</span>
      ) : (
        <>
          <span className={`timingHeadline ${toneOf(window.mean_days)}`}>
            {headline(window.mean_days)}
          </span>
          <span className="small-text muted timingOnTime">
            {window.on_time_percent}% on time · {window.counted}{" "}
            {window.counted === 1 ? "task" : "tasks"}
          </span>
          <span className="small-text muted timingSplit">{splitLine(window)}</span>
        </>
      )}
    </div>
  );
}

/** "1.2 days early", "half a day late", "on time". */
function headline(meanDays: number | null): string {
  if (meanDays === null) return "on time";

  const size = Math.abs(meanDays);
  // Rounded to a tenth by the API, so anything under 0.05 is genuinely nothing
  // rather than a figure too small to print.
  if (size < 0.05) return "On time, on average";

  return `${size} ${size === 1 ? "day" : "days"} ${meanDays > 0 ? "late" : "early"}`;
}

function splitLine(window: TimingWindow): string {
  const parts: string[] = [];
  if (window.early_count > 0) {
    parts.push(`${window.early_count} early by ${window.early_mean_days}`);
  }
  if (window.late_count > 0) {
    parts.push(`${window.late_count} late by ${window.late_mean_days}`);
  }
  return parts.length > 0 ? parts.join(" · ") : "all exactly on the day";
}

/** Late is worth noticing; early and on-time are not worth colouring. */
function toneOf(meanDays: number | null): string {
  return meanDays !== null && meanDays > 0.05 ? "timingHeadlineLate" : "";
}
