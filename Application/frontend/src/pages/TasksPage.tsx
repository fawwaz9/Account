import { useEffect, useMemo, useState } from "react";
import TaskList from "../features/tasks/components/TaskList";
import TaskForm from "../features/tasks/components/TaskForm";
import { useTasks } from "../features/tasks/hooks/useTasks";
import { createTask, deleteTask, setTaskDone } from "../features/tasks/api";
import { Task, TaskCreate } from "../features/tasks/types";
import { fetchCourses } from "../features/grades/api";
import { Course } from "../features/grades/types";
import { useAuth } from "../app/auth/AuthContext";
import { daysBetween, today } from "../shared/utils/dateUtils";
import "../styles/calendar.css";
import "../styles/tasks.css";

/**
 * Work due inside this many days gets its own section.
 *
 * Two weeks because that is the window an assignment is actually actionable in.
 * Exams are not tasks -- they are events with a date and a room, so the
 * thirty-day exam view belongs on the calendar rather than here.
 */
const ASSIGNMENT_HORIZON = 14;

export default function TasksPage() {
  const { user } = useAuth();
  const [showDone, setShowDone] = useState(false);
  const { tasks, loading, error, reload } = useTasks({
    includeDone: showDone,
    includeArchived: showDone,
  });

  const [courses, setCourses] = useState<Course[]>([]);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;

    let mounted = true;
    fetchCourses(user.id)
      .then((next) => { if (mounted) setCourses(next); })
      .catch(() => { if (mounted) setCourses([]); });

    return () => { mounted = false; };
  }, [user]);

  // Grouped by how soon, not by course: the question this page answers is
  // "what now", and a course grouping answers "what eventually".
  const groups = useMemo(() => groupByHorizon(tasks), [tasks]);

  async function withBusy(action: () => Promise<unknown>, failure: string) {
    setBusy(true);
    setActionError(null);
    try {
      await action();
      await reload();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : failure);
    } finally {
      setBusy(false);
    }
  }

  async function handleAdd(task: TaskCreate) {
    if (!user) return;
    await withBusy(() => createTask(user.id, task), "Could not add the task");
  }

  async function handleToggle(task: Task) {
    if (!user) return;
    await withBusy(() => setTaskDone(user.id, task.id, !task.done), "Could not update the task");
  }

  async function handleDelete(task: Task) {
    if (!user) return;
    await withBusy(() => deleteTask(user.id, task.id), "Could not delete the task");
  }

  return (
    <div className="container">
      <div className="calTopbar">
        <h1 className="title">Tasks</h1>
        <label className="taskToggle">
          <input
            type="checkbox"
            checked={showDone}
            onChange={(event) => setShowDone(event.target.checked)}
          />
          Show completed
        </label>
      </div>

      <TaskForm courses={courses} onSubmit={handleAdd} busy={busy} />

      {error && <p className="calError">{error}</p>}
      {actionError && <p className="calError">{actionError}</p>}
      {loading && <p className="calMuted" role="status">Loading…</p>}

      <TaskList
        title="Overdue"
        tasks={groups.overdue}
        onToggle={handleToggle}
        onDelete={handleDelete}
        busy={busy}
        emptyMessage="Nothing overdue."
      />
      <TaskList
        title={`Due in the next ${ASSIGNMENT_HORIZON} days`}
        tasks={groups.soon}
        onToggle={handleToggle}
        onDelete={handleDelete}
        busy={busy}
        emptyMessage="Clear for a fortnight."
      />
      <TaskList
        title="Later"
        tasks={groups.later}
        onToggle={handleToggle}
        onDelete={handleDelete}
        busy={busy}
        emptyMessage="Nothing on the horizon."
      />
      <TaskList
        title="No date"
        tasks={groups.undated}
        onToggle={handleToggle}
        onDelete={handleDelete}
        busy={busy}
        emptyMessage="Nothing without a date."
      />
      {showDone && (
        <TaskList
          title="Done"
          tasks={groups.done}
          onToggle={handleToggle}
          onDelete={handleDelete}
          busy={busy}
          emptyMessage="Nothing finished yet."
        />
      )}
    </div>
  );
}

interface TaskGroups {
  overdue: Task[];
  soon: Task[];
  later: Task[];
  undated: Task[];
  done: Task[];
}

/**
 * Sort tasks into how-soon buckets.
 *
 * Anything past its date leads, because that is the only group where the answer
 * changes what you do in the next hour. Completed tasks leave every other group
 * so a finished assignment does not sit in "overdue" forever.
 */
function groupByHorizon(tasks: Task[]): TaskGroups {
  const now = today();
  const groups: TaskGroups = { overdue: [], soon: [], later: [], undated: [], done: [] };

  for (const task of tasks) {
    if (task.done) {
      groups.done.push(task);
      continue;
    }
    if (!task.due_date) {
      groups.undated.push(task);
      continue;
    }

    const days = daysBetween(now, task.due_date);
    if (days < 0) groups.overdue.push(task);
    else if (days <= ASSIGNMENT_HORIZON) groups.soon.push(task);
    else groups.later.push(task);
  }

  return groups;
}
