import { Task } from "../types";
import TaskItem from "./TaskItem";
import { duration } from "../../../shared/utils/dateUtils";

/** A group's title and tasks, the row handlers, and the empty and loading states. */
interface TaskListProps {
  readonly title: string;
  readonly tasks: Task[];
  readonly onToggle: (task: Task) => void;
  readonly onEdit: (task: Task) => void;
  readonly onDelete: (task: Task) => void;
  readonly onPriority: (task: Task, priority: number) => void;
  readonly onSnooze: (task: Task) => void;
  readonly onWake: (task: Task) => void;
  /** Start or stop a task's timer. Without it, rows show no timer control. */
  readonly onTimer?: (task: Task) => void;
  readonly busy: boolean;
  readonly emptyMessage?: string;
  /** Rows still loading: with none to show, the count and empty text give way to Loading. */
  readonly loading?: boolean;
}

/** A titled group of task rows; the heading gives the count and the total estimated time. */
export default function TaskList({
  title,
  tasks,
  onToggle,
  onEdit,
  onDelete,
  onPriority,
  onSnooze,
  onWake,
  onTimer,
  busy,
  emptyMessage = "Nothing here.",
  loading = false,
}: TaskListProps) {
  const estimated = tasks.reduce((total, task) => total + (task.estimated_minutes ?? 0), 0);
  const load = duration(estimated);
  // Only while there is nothing to show. A reload with rows already on screen
  // keeps them: they are still the answer, and swapping them for a spinner
  // would make the page restless for no information gained.
  const awaiting = loading && tasks.length === 0;

  return (
    <section className="taskGroup">
      <header className="taskGroupHeader">
        <h2 className="taskGroupTitle">{title}</h2>
        {/* No count while waiting. "0 tasks" beside "Loading..." is the same
            false claim as the empty message, in fewer words. */}
        {!awaiting && (
          <span className="taskGroupCount">
            {tasks.length} {tasks.length === 1 ? "task" : "tasks"}
            {load && ` · ${load}`}
          </span>
        )}
      </header>

      {tasks.length === 0 ? (
        <p className="taskEmpty" role={awaiting ? "status" : undefined}>
          {awaiting ? "Loading\u2026" : emptyMessage}
        </p>
      ) : (
        <ul className="taskItems">
          {tasks.map((task) => (
            <TaskItem
              key={task.id}
              task={task}
              onToggle={onToggle}
              onEdit={onEdit}
              onDelete={onDelete}
              onPriority={onPriority}
              onSnooze={onSnooze}
              onWake={onWake}
              onTimer={onTimer}
              busy={busy}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
