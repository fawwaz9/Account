import { RecurringTask } from "../types";
import { dueLabel, duration, shortDate } from "../../../shared/utils/dateUtils";

const WEEKDAY_NAMES: Record<string, string> = {
  MO: "Mon", TU: "Tue", WE: "Wed", TH: "Thu", FR: "Fri", SA: "Sat", SU: "Sun",
};

/** The rule in words: "every Monday", "every 2 weeks, 6 times". */
function ruleInWords(rule: RecurringTask): string {
  const { freq, interval, byday } = rule.recurrence;
  const unit = freq === "daily" ? "day" : freq === "weekly" ? "week" : "month";

  let base: string;
  if (freq === "weekly" && byday.length > 0 && interval === 1) {
    // "every Mon, Wed" reads better than "every week on Mon, Wed".
    base = `every ${byday.map((day) => WEEKDAY_NAMES[day] ?? day).join(", ")}`;
  } else {
    base = interval === 1 ? `every ${unit}` : `every ${interval} ${unit}s`;
  }

  if (rule.recurrence.until) return `${base}, until ${shortDate(rule.recurrence.until)}`;
  if (rule.recurrence.count) return `${base}, ${rule.recurrence.count} times`;
  return base;
}

interface RepeatingProps {
  readonly rules: RecurringTask[];
  readonly onAdd: () => void;
  readonly onEdit: (rule: RecurringTask) => void;
  readonly onStop: (rule: RecurringTask) => void;
  readonly busy: boolean;
}

/**
 * The repeats themselves, listed apart from the tasks they produce.
 *
 * Two lists rather than one, because they answer different questions: the task
 * list is what to do this week, and this is what keeps coming back. Showing a
 * rule inline among its own occurrences would make it look like a seventh thing
 * to tick off.
 */
export default function Repeating({ rules, onAdd, onEdit, onStop, busy }: RepeatingProps) {
  const weekly = rules
    .filter((rule) => rule.active && rule.estimated_minutes)
    .reduce((total, rule) => total + (rule.estimated_minutes ?? 0), 0);

  return (
    <section className="taskGroup repeatingSection">
      <header className="taskGroupHeader">
        <h2 className="taskGroupTitle">Repeats</h2>
        <div className="repeatingHeaderRight">
          {weekly > 0 && (
            <span className="taskGroupCount">{duration(weekly)} each time round</span>
          )}
          <button type="button" className="calButton" onClick={onAdd} disabled={busy}>
            Add
          </button>
        </div>
      </header>

      {rules.length === 0 ? (
        <p className="taskEmpty">
          Nothing repeating yet. A chore set up here writes itself into the list
          each time it comes round, and each one is ticked off on its own.
        </p>
      ) : (
        <ul className="taskItems">
          {rules.map((rule) => (
            <li
              key={rule.id}
              className={rule.active ? "taskRow" : "taskRow taskRowDone"}
            >
              <div className="taskBody">
                <p className="taskTitle">
                  {rule.title}
                  {!rule.active && <span className="muted"> · paused</span>}
                </p>
                <div className="taskMeta">
                  {rule.course_code && (
                    <span className="taskTag taskTagCourse">{rule.course_code}</span>
                  )}
                  {rule.tags.map((tag) => (
                    <span key={tag} className="taskTag">{tag}</span>
                  ))}
                  <span className="taskRepeatRule">{ruleInWords(rule)}</span>
                  {rule.active && rule.next_due_on && (
                    <span className="taskDue">next {dueLabel(rule.next_due_on)}</span>
                  )}
                  {rule.estimated_minutes && (
                    <span className="taskEstimate">{duration(rule.estimated_minutes)}</span>
                  )}
                </div>
              </div>

              <div className="repeatingActions">
                <button
                  type="button"
                  className="calButton"
                  onClick={() => onEdit(rule)}
                  disabled={busy}
                  aria-label={`Edit ${rule.title}`}
                >
                  Edit
                </button>
                <button
                  type="button"
                  className="calButton calButtonDanger"
                  onClick={() => onStop(rule)}
                  disabled={busy}
                  aria-label={`Stop ${rule.title} repeating`}
                >
                  Stop
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
