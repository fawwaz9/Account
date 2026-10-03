import { Task } from "./types";
import { daysBetween, today } from "../../shared/utils/dateUtils";

/**
 * Which horizon a task falls into, and what a just-ticked row does.
 *
 * Lifted out of `TasksPage` once the rule stopped being a one-liner: a completed
 * task used to leave its group in the same frame the save landed, so the tick was
 * never visible. The linger below is what makes it visible, and it is the kind of
 * rule that is worth a test rather than a careful read.
 */

/** The fortnight the assignment list covers. */
export const ASSIGNMENT_HORIZON = 14;

/**
 * How long a just-ticked task stays on screen, crossed out, before it leaves the
 * group it was in. 300ms: long enough to read as "that registered", short enough
 * that nobody waits for it.
 */
export const DONE_LINGER_MS = 300;

export interface TaskGroups {
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
export function groupByHorizon(tasks: Task[], justChecked: ReadonlySet<string>): TaskGroups {
  const now = today();
  const groups: TaskGroups = { overdue: [], soon: [], later: [], undated: [], done: [] };

  for (const task of tasks) {
    // A row inside its linger window is shown *done* but filed where it already
    // was, so the tick and the line through the title are visible for a moment
    // before it moves. `done: true` is set locally rather than waited for, which
    // is what makes the feedback immediate; `.taskRowDone` already carries both
    // the strike-through and the fade.
    const lingering = justChecked.has(task.id);
    const row = lingering ? { ...task, done: true } : task;

    if (row.done && !lingering) {
      groups.done.push(row);
      continue;
    }
    if (!row.due_date) {
      groups.undated.push(row);
      continue;
    }

    const days = daysBetween(now, row.due_date);
    if (days < 0) groups.overdue.push(row);
    else if (days <= ASSIGNMENT_HORIZON) groups.soon.push(row);
    else groups.later.push(row);
  }

  return groups;
}

/** A set without one id, returning the original when there is nothing to remove
 *  so an unrelated toggle does not re-render every group. */
export function withoutId(ids: ReadonlySet<string>, id: string): ReadonlySet<string> {
  if (!ids.has(id)) return ids;
  const next = new Set(ids);
  next.delete(id);
  return next;
}
