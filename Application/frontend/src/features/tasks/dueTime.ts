import { Task } from "./types";

/**
 * What a due date means when no time is given: the end of that day.
 *
 * A deadline with no time is really "by the end of Friday", so this is what a
 * date pre-fills with rather than leaving the time null.
 */
export const END_OF_DAY = "23:59";

/**
 * Is this the end-of-day sentinel rather than a time someone chose?
 *
 * The API sends HH:MM:SS and the form produces HH:MM, so both are accepted.
 */
export function isEndOfDay(dueTime: string | null): boolean {
  return dueTime !== null && dueTime.slice(0, 5) === END_OF_DAY;
}

/**
 * Does this task claim a particular moment of the day?
 *
 * The one predicate behind both halves of the week view, and it has to stay
 * that way. The grid draws the tasks this is true of and the all-day band draws
 * the rest; if the two ever disagree a task either shows up twice or silently
 * disappears, which is exactly the kind of fault a calendar makes invisible.
 *
 * End of day counts as no particular time. It is what a bare due date fills in,
 * so treating it as a real deadline would pile almost every task onto the last
 * minute of the day -- below the fold, clustered, and saying nothing the date
 * did not already say.
 */
export function hasSpecificTime(task: Pick<Task, "due_time">): boolean {
  return task.due_time !== null && !isEndOfDay(task.due_time);
}
