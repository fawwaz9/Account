import { useEffect, useMemo, useState } from "react";
import TaskList from "../features/tasks/components/TaskList";
import TaskForm from "../features/tasks/components/TaskForm";
import QuickCapture from "../features/tasks/components/QuickCapture";
import Repeating from "../features/tasks/components/Repeating";
import RepeatingModal from "../features/tasks/components/RepeatingModal";
import ExamStrip from "../features/tasks/components/ExamStrip";
import CompletionTimingBlock from "../features/tasks/components/CompletionTiming";
import SnoozeModal from "../features/tasks/components/SnoozeModal";
import EditTaskModal from "../features/tasks/components/EditTaskModal";
import ReminderBanner from "../features/tasks/components/ReminderBanner";
import ReminderModal from "../features/tasks/components/ReminderModal";
import DeleteConfirmModal from "../features/grades/components/DeleteConfirmModal";
import {
  ASSIGNMENT_HORIZON,
  DONE_LINGER_MS,
  groupByHorizon,
  withoutId,
} from "../features/tasks/horizon";
import { useTasks } from "../features/tasks/hooks/useTasks";
import { useReminders } from "../features/tasks/hooks/useReminders";
import {
  createTask,
  deleteRepeating,
  deleteTask,
  fetchTaskTiming,
  setTaskDone,
  updateTask,
  wakeTask,
} from "../features/tasks/api";
import {
  CompletionTiming,
  RecurringTask,
  Task,
  TaskCreate,
} from "../features/tasks/types";
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
 * There is deliberately no section past it: a task three weeks out is not work
 * you can start, and a standing list of it was noise above the part that is.
 * The count of what lies beyond is still shown, so nothing is silently hidden.
 * Exams are still not tasks -- there is nothing to tick off, so they are not
 * rows in these groups. They are a read-only band above the list instead
 * (ExamStrip), on a thirty-day horizon: revision is what fills the fortnight,
 * so knowing what it is for has to reach further out than the work itself.
 */

export default function TasksPage() {
  const { user } = useAuth();
  const [showDone, setShowDone] = useState(false);
  const { tasks, repeating, loading, error, reload } = useTasks({
    includeDone: showDone,
    includeArchived: showDone,
  });

  const [courses, setCourses] = useState<Course[]>([]);
  const [timing, setTiming] = useState<CompletionTiming | null>(null);
  const [snoozing, setSnoozing] = useState<Task | null>(null);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [remindersOpen, setRemindersOpen] = useState(false);
  const { due: dueReminders, dismiss: dismissDue, refresh: refreshReminders } =
    useReminders();
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [editingRule, setEditingRule] = useState<RecurringTask | null>(null);
  const [addingRule, setAddingRule] = useState(false);

  useEffect(() => {
    if (!user) return;

    let mounted = true;
    fetchCourses(user.id)
      .then((next) => { if (mounted) setCourses(next); })
      .catch(() => { if (mounted) setCourses([]); });

    return () => { mounted = false; };
  }, [user]);

  // Refetched whenever the list reloads, because ticking a task off is exactly
  // what moves these figures.
  useEffect(() => {
    if (!user) return;

    let mounted = true;
    fetchTaskTiming(user.id)
      .then((next) => { if (mounted) setTiming(next); })
      .catch(() => { if (mounted) setTiming(null); });

    return () => { mounted = false; };
  }, [user, tasks]);

  // Grouped by how soon, not by course: the question this page answers is
  // "what now", and a course grouping answers "what eventually".
  // Ids ticked off but deliberately still shown, crossed out, in the group they
  // were already in. Without this a completed task leaves the fortnight in the
  // same frame the server answers in, so the tick never appears on screen at all.
  const [justChecked, setJustChecked] = useState<ReadonlySet<string>>(new Set());
  // Both deletes here are permanent and neither asked before. A task has no
  // restore path, and "Stop" on a repeat calls deleteRepeating despite the word.
  const [deletingTask, setDeletingTask] = useState<Task | null>(null);
  const [stoppingRule, setStoppingRule] = useState<RecurringTask | null>(null);
  const groups = useMemo(() => groupByHorizon(tasks, justChecked), [tasks, justChecked]);

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

    // Re-opening needs no ceremony: the row is arriving, not leaving. Drop any
    // lingering tick first so unchecking inside the linger window is immediate.
    if (task.done) {
      setJustChecked((prev) => withoutId(prev, task.id));
      await withBusy(() => setTaskDone(user.id, task.id, false), "Could not update the task");
      return;
    }

    // Marked done locally first, so the tick and the strike-through land on the
    // click rather than after the round trip. The linger runs alongside the
    // request rather than after it, so the row is held for DONE_LINGER_MS *or*
    // the request, whichever is slower -- a slow network does not add delay on
    // top of the pause, and a fast one still shows the tick.
    setJustChecked((prev) => new Set(prev).add(task.id));
    const linger = new Promise((resolve) => setTimeout(resolve, DONE_LINGER_MS));
    try {
      await withBusy(() => setTaskDone(user.id, task.id, true), "Could not update the task");
    } finally {
      await linger;
      // Cleared whether the save worked or not: on failure the reload has already
      // put the row back undone, and holding a false tick would be worse than
      // losing the animation.
      setJustChecked((prev) => withoutId(prev, task.id));
    }
  }

  async function handleDelete(task: Task) {
    if (!user) return;
    setDeletingTask(null);
    await withBusy(() => deleteTask(user.id, task.id), "Could not delete the task");
  }

  async function handlePriority(task: Task, priority: number) {
    if (!user) return;
    await withBusy(
      () => updateTask(user.id, task.id, { priority }),
      "Could not change the priority"
    );
  }

  async function handleWake(task: Task) {
    if (!user) return;
    await withBusy(() => wakeTask(user.id, task.id), "Could not bring that back");
  }

  async function handleStopRepeat(rule: RecurringTask) {
    if (!user) return;
    setStoppingRule(null);
    // Occurrences already ticked off stay: they record work actually done.
    await withBusy(
      () => deleteRepeating(user.id, rule.id),
      "Could not stop that repeat"
    );
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
        <button
          type="button"
          className="calButton"
          onClick={() => setRemindersOpen(true)}
        >
          Reminders
        </button>
      </div>

      {/* Full width, above the split: it is a scrolling row of cards that wants
          the room, and what is coming is context for both columns rather than
          belonging to either. */}
      <ReminderBanner due={dueReminders} onDismiss={dismissDue} />

      <ExamStrip />

      {error && <p className="calError">{error}</p>}
      {actionError && <p className="calError">{actionError}</p>}
      {loading && <p className="calMuted" role="status">Loading…</p>}

      {/*
        Two columns, split by what you do with them rather than by size.

        The left is the work in front of you -- how you have been doing, the one
        line it takes to add something, what is late, what has no date at all,
        and the record of what is finished. The right is everything that takes
        more than a line: the full form, the repeats that write themselves, and
        the fortnight they write into.

        Each column is its own flex column rather than the grid placing rows,
        because a grid row is as tall as its tallest cell -- a short "Overdue"
        beside a long fortnight would leave a hole under it.
      */}
      <div className="taskGrid">
        <div className="taskCol">
          <div className="taskSlot taskSlot--stats">
            <CompletionTimingBlock timing={timing} />
          </div>

          <div className="taskSlot taskSlot--capture">
            <QuickCapture onCaptured={reload} />
          </div>

          <div className="taskSlot taskSlot--overdue">
            <TaskList
              title="Overdue"
              tasks={groups.overdue}
              onToggle={handleToggle}
              onEdit={setEditingTask}
              onDelete={setDeletingTask}
              onPriority={handlePriority}
              onSnooze={setSnoozing}
              onWake={handleWake}
              busy={busy}
              emptyMessage="Nothing overdue."
            />
          </div>

          <div className="taskSlot taskSlot--undated">
            <TaskList
              title="No date"
              tasks={groups.undated}
              onToggle={handleToggle}
              onEdit={setEditingTask}
              onDelete={setDeletingTask}
              onPriority={handlePriority}
              onSnooze={setSnoozing}
              onWake={handleWake}
              busy={busy}
              emptyMessage="Nothing without a date."
            />
          </div>

          {showDone && (
            <div className="taskSlot taskSlot--done">
              <TaskList
                title="Done"
                tasks={groups.done}
                onToggle={handleToggle}
                onEdit={setEditingTask}
                onDelete={setDeletingTask}
                onPriority={handlePriority}
                onSnooze={setSnoozing}
                onWake={handleWake}
                busy={busy}
                emptyMessage="Nothing finished yet."
              />
            </div>
          )}
        </div>

        <div className="taskCol">
          {/* The fast path is the add bar on the left; this is the same act with
              every field, for the tasks that need them. */}
          <div className="taskSlot taskSlot--form">
            <details className="captureDetails">
              <summary className="captureSummary">Add with all the fields</summary>
              <TaskForm courses={courses} onSubmit={handleAdd} busy={busy} />
            </details>
          </div>

          <div className="taskSlot taskSlot--repeats">
            <Repeating
              rules={repeating}
              onAdd={() => { setEditingRule(null); setAddingRule(true); }}
              onEdit={(rule) => { setEditingRule(rule); setAddingRule(true); }}
              onStop={setStoppingRule}
              busy={busy}
            />
          </div>

          <div className="taskSlot taskSlot--soon">
            <TaskList
              title={`Due in the next ${ASSIGNMENT_HORIZON} days`}
              tasks={groups.soon}
              onToggle={handleToggle}
              onEdit={setEditingTask}
              onDelete={setDeletingTask}
              onPriority={handlePriority}
              onSnooze={setSnoozing}
              onWake={handleWake}
              busy={busy}
              emptyMessage="Clear for a fortnight."
            />
            {/* Under the list it qualifies, so the fortnight is not read as
                everything there is. */}
            {groups.later.length > 0 && (
              <p className="small-text muted taskBeyond">
                {groups.later.length} further out than {ASSIGNMENT_HORIZON} days, on the calendar.
              </p>
            )}
          </div>
        </div>
      </div>

      <ReminderModal
        open={remindersOpen}
        courses={courses}
        onClose={() => setRemindersOpen(false)}
        onSaved={refreshReminders}
      />

      <SnoozeModal
        task={snoozing}
        onClose={() => setSnoozing(null)}
        onSaved={reload}
      />

      {/* One editor for four lists. The calendar opens this same component,
          deliberately: two dialogs for one record is how the two end up
          offering different fields. */}
      <EditTaskModal
        task={editingTask}
        courses={courses}
        onClose={() => setEditingTask(null)}
        onSaved={reload}
      />

      <RepeatingModal
        open={addingRule}
        rule={editingRule}
        courses={courses}
        onClose={() => { setAddingRule(false); setEditingRule(null); }}
        onSaved={reload}
      />
    </div>
  );
}

