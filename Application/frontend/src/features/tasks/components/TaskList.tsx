import { Task } from "../types";
import TaskItem from "./TaskItem";
import { duration } from "../../../shared/utils/dateUtils";

interface TaskListProps {
  readonly title: string;
  readonly tasks: Task[];
  readonly onToggle: (task: Task) => void;
  readonly onDelete: (task: Task) => void;
  readonly onPriority: (task: Task, priority: number) => void;
  readonly onSnooze: (task: Task) => void;
  readonly onWake: (task: Task) => void;
  readonly busy: boolean;
  readonly emptyMessage?: string;
}

/**
 * A titled group of tasks, with what the group costs.
 *
 * The heading carries hours rather than only a count, because "7 tasks" says
 * nothing about whether the week fits and "23 hours" says it immediately.
 */
export default function TaskList({
  title,
  tasks,
  onToggle,
  onDelete,
  onPriority,
  onSnooze,
  onWake,
  busy,
  emptyMessage = "Nothing here.",
}: TaskListProps) {
  const estimated = tasks.reduce((total, task) => total + (task.estimated_minutes ?? 0), 0);
  const load = duration(estimated);

  return (
    <section className="taskGroup">
      <header className="taskGroupHeader">
        <h2 className="taskGroupTitle">{title}</h2>
        <span className="taskGroupCount">
          {tasks.length} {tasks.length === 1 ? "task" : "tasks"}
          {load && ` · ${load}`}
        </span>
      </header>

      {tasks.length === 0 ? (
        <p className="taskEmpty">{emptyMessage}</p>
      ) : (
        <ul className="taskItems">
          {tasks.map((task) => (
            <TaskItem
              key={task.id}
              task={task}
              onToggle={onToggle}
              onDelete={onDelete}
              onPriority={onPriority}
              onSnooze={onSnooze}
              onWake={onWake}
              busy={busy}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
