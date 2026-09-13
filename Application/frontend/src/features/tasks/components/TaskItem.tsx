import { MAX_PRIORITY, MIN_PRIORITY, PRIORITY_LABELS, RiskBand, Task } from "../types";
import { dueLabel, duration, daysBetween, today } from "../../../shared/utils/dateUtils";

/**
 * What each band says when you hover it.
 *
 * The badge itself is a single character: a task row already carries a course
 * code, a date, an estimate and sometimes a tag, and a fourth word competing
 * with those buries the thing it is meant to surface.
 */
const RISK_TITLES: Record<RiskBand, string> = {
  mild: "This course is slightly below its target",
  moderate: "This course is well below its target",
  severe: "This course is far below its target",
};

/** 1..5, for the select. */
const PRIORITY_STEPS = Array.from(
  { length: MAX_PRIORITY - MIN_PRIORITY + 1 },
  (_, index) => MIN_PRIORITY + index
);

interface TaskItemProps {
  readonly task: Task;
  readonly onToggle: (task: Task) => void;
  readonly onDelete: (task: Task) => void;
  readonly onPriority: (task: Task, priority: number) => void;
  readonly onSnooze: (task: Task) => void;
  readonly onWake: (task: Task) => void;
  readonly busy: boolean;
}

/**
 * One row of the task list.
 *
 * The checkbox and the delete control are separate elements rather than one row
 * that does both, so a single click can never mean two things (SonarQube S6848,
 * and the same rule the ledger rows follow).
 */
export default function TaskItem({
  task,
  onToggle,
  onDelete,
  onPriority,
  onSnooze,
  onWake,
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
          5 to 4 a four-click job. */}
      <select
        className={`taskPriority taskPriority-${task.priority}`}
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
          {/* A task the gradebook owns closes itself when the score lands, so
              saying where it came from explains why it cannot be deleted here. */}
          {task.grade_id && <span className="taskTag taskTagAuto">from grades</span>}
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
