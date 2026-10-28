import { MAX_PRIORITY, MIN_PRIORITY, PRIORITY_LABELS, RiskBand, Task } from "../types";
import { dueLabel, duration, daysBetween, today } from "../../../shared/utils/dateUtils";

/** Hover and accessible text for each risk band's one-character badge. */
const RISK_TITLES: Record<RiskBand, string> = {
  mild: "This course is slightly below its target",
  moderate: "This course is well below its target",
  severe: "This course is far below its target",
};

/** Every priority step, lowest first, for the select. */
const PRIORITY_STEPS = Array.from(
  { length: MAX_PRIORITY - MIN_PRIORITY + 1 },
  (_, index) => MIN_PRIORITY + index
);

/** The task, its row action handlers, and a busy flag. */
interface TaskItemProps {
  readonly task: Task;
  readonly onToggle: (task: Task) => void;
  readonly onEdit: (task: Task) => void;
  readonly onDelete: (task: Task) => void;
  readonly onPriority: (task: Task, priority: number) => void;
  readonly onSnooze: (task: Task) => void;
  readonly onWake: (task: Task) => void;
  readonly onTimer?: (task: Task) => void;
  readonly busy: boolean;
}

/** A running timer's start as a browser-local clock time; the server sends naive UTC. */
function timerSince(startedAt: string): string {
  // Stored naive in UTC, so it usually arrives with no offset; without the Z,
  // the browser would read it as local time and be hours out.
  const stamp = /(?:[zZ]|[+-]\d\d:?\d\d)$/.test(startedAt) ? startedAt : `${startedAt}Z`;
  return new Date(stamp).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

/** One task row: tick, priority select, details and badges, then edit, timer, snooze, delete. */
export default function TaskItem({
  task,
  onToggle,
  onEdit,
  onDelete,
  onPriority,
  onSnooze,
  onWake,
  onTimer,
  busy,
}: TaskItemProps) {
  const overdue = !task.done && task.due_date !== null && daysBetween(today(), task.due_date) < 0;
  const estimate = duration(task.estimated_minutes);

  return (
    <li className={`taskRow${task.done ? " taskRowDone" : ""}${overdue ? " taskRowOverdue" : ""}`}>
      <button
        type="button"
        className="taskCheck"
        onClick={() => onToggle(task)}
        disabled={busy}
        aria-pressed={task.done}
        aria-label={`${task.done ? "Reopen" : "Complete"} ${task.title}`}
      >
        <span aria-hidden="true">{task.done ? "✓" : ""}</span>
      </button>

      {/* A select rather than a badge you click through: coursework arrives with
          a priority already on it, so the common interaction is correcting one
          rather than setting one, and a cycle-on-click control makes going from
          5 to 4 a four-click job. The select's own text is transparent and a
          centred span sits over it showing just the number -- the closed badge
          stays a clean digit while the open menu still explains what each step
          means. */}
      <span className={`taskPriorityWrap taskPriority-${task.priority}`}>
        <select
          className="taskPriority"
          value={task.priority}
          onChange={(event) => onPriority(task, Number(event.target.value))}
          disabled={busy}
          title={`Priority: ${PRIORITY_LABELS[task.priority]}`}
          aria-label={`Priority of ${task.title}`}
        >
          {PRIORITY_STEPS.map((step) => (
            <option key={step} value={step}>
              {step} · {PRIORITY_LABELS[step]}
            </option>
          ))}
        </select>
        <span className="taskPriorityBadge" aria-hidden="true">{task.priority}</span>
      </span>

      <div className="taskBody">
        <p className="taskTitle">{task.title}</p>

        <div className="taskMeta">
          {/* Beside the course code, because the course is what is at risk --
              the task itself is fine, it is the thing it belongs to that is
              slipping. */}
          {task.risk && (
            <span
              className={`taskRisk taskRisk-${task.risk}`}
              title={RISK_TITLES[task.risk]}
              aria-label={RISK_TITLES[task.risk]}
            >
              <span aria-hidden="true">!</span>
            </span>
          )}
          {task.course_code && <span className="taskTag taskTagCourse">{task.course_code}</span>}
          {task.tags.map((tag) => (
            <span key={tag} className="taskTag">{tag}</span>
          ))}
          {task.due_date && (
            <span className={overdue ? "taskDue taskDueOverdue" : "taskDue"}>
              {dueLabel(task.due_date)}
            </span>
          )}
          {estimate && <span className="taskEstimate">{estimate}</span>}
          {/* What it actually took, once said: beside the estimate so the two
              read as a pair. */}
          {task.actual_minutes != null && (
            <span className="taskEstimate taskActual">took {duration(task.actual_minutes)}</span>
          )}
          {task.timer_started_at && (
            <span className="taskTag taskTagTimer" role="status">
              timing since {timerSince(task.timer_started_at)}
            </span>
          )}
          {/* A task the gradebook owns closes itself when the score lands, so
              saying where it came from explains why it cannot be deleted here. */}
          {task.grade_id && <span className="taskTag taskTagAuto">from grades</span>}
          {/* Phase 2 item 9a: anyone on it can tick it and edit its text. */}
          {task.shared_with && task.shared_with.length > 0 && (
            <span className="taskTag taskTagShared">with {task.shared_with.join(", ")}</span>
          )}
          {/* The count, not the history: the fourth time you push something back
              for the same reason, the reason is the problem. */}
          {task.snooze_count > 0 && (
            <span
              className="taskTag taskTagSnoozed"
              title={task.last_snooze_reason ?? "No reason given"}
            >
              snoozed {task.snooze_count}x
            </span>
          )}
        </div>

        {task.notes && <p className="taskNotes">{task.notes}</p>}
      </div>

      {/* Offered on a finished task as well as an outstanding one: a title
          typed wrongly is still wrong after it is ticked off, and this is the
          only way to fix one. */}
      <button
        type="button"
        className="taskEdit"
        onClick={() => onEdit(task)}
        disabled={busy}
        aria-label={`Edit ${task.title}`}
      >
        Edit
      </button>

      {!task.done && onTimer && (
        <button
          type="button"
          className="taskTimer"
          onClick={() => onTimer(task)}
          disabled={busy}
          aria-pressed={Boolean(task.timer_started_at)}
          aria-label={`${task.timer_started_at ? "Stop timing" : "Time"} ${task.title}`}
        >
          {task.timer_started_at ? "Stop" : "Time"}
        </button>
      )}

      {!task.done && (
        <button
          type="button"
          className="taskSnooze"
          onClick={() => (task.snoozed_until ? onWake(task) : onSnooze(task))}
          disabled={busy}
          aria-label={
            task.snoozed_until
              ? `Bring back ${task.title}`
              : `Snooze ${task.title}`
          }
        >
          {task.snoozed_until ? "Bring back" : "Snooze"}
        </button>
      )}

      {task.grade_id ? (
        <span className="taskMuted" title="Delete the grade to remove this task">—</span>
      ) : (
        <button
          type="button"
          className="taskDelete"
          onClick={() => onDelete(task)}
          disabled={busy}
          aria-label={`Delete ${task.title}`}
        >
          Delete
        </button>
      )}
    </li>
  );
}
