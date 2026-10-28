import { Task } from "./types";
import { daysBetween, today } from "../../shared/utils/dateUtils";

/** Groups tasks by how soon they fall due, with a short linger for a just-ticked row. */

/** Days ahead the "soon" group covers. */
export const ASSIGNMENT_HORIZON = 14;

/** How long a just-ticked task stays in its group, crossed out, before moving to done (ms). */
export const DONE_LINGER_MS = 300;

/** Tasks sorted into overdue, soon, later, undated and done. */
export interface TaskGroups {
  overdue: Task[];
  soon: Task[];
  later: Task[];
  undated: Task[];
  done: Task[];
}

/** Sort tasks into horizon groups against today; ids in `justChecked` show done but stay put. */
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

/** `ids` without `id`; the same set back when it wasn't there, so nothing re-renders. */
export function withoutId(ids: ReadonlySet<string>, id: string): ReadonlySet<string> {
  if (!ids.has(id)) return ids;
  const next = new Set(ids);
  next.delete(id);
  return next;
}
