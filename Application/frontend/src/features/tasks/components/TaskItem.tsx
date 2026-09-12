import { RiskBand, Task } from "../types";
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

interface TaskItemProps {
  readonly task: Task;
  readonly onToggle: (task: Task) => void;
  readonly onDelete: (task: Task) => void;
  readonly busy: boolean;
}

/**
 * One row of the task list.
 *
 * The checkbox and the delete control are separate elements rather than one row
 * that does both, so a single click can never mean two things (SonarQube S6848,
 * and the same rule the ledger rows follow).
 */
export default function TaskItem({ task, onToggle, onDelete, busy }: TaskItemProps) {
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
        </div>

        {task.notes && <p className="taskNotes">{task.notes}</p>}
      </div>

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
