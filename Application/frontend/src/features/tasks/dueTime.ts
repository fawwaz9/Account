import { Task } from "./types";

/** What a bare due date means, the end of that day; date-only deadlines are filled with it. */
export const END_OF_DAY = "23:59";

/** True when a time is the end-of-day sentinel; accepts "HH:MM" and "HH:MM:SS". */
export function isEndOfDay(dueTime: string | null): boolean {
  return dueTime !== null && dueTime.slice(0, 5) === END_OF_DAY;
}

/**
 * True when a task is due at a chosen time, neither none nor the end-of-day sentinel.
 * The week grid and its all-day band split tasks on this alone, so they never overlap.
 */
export function hasSpecificTime(task: Pick<Task, "due_time">): boolean {
  return task.due_time !== null && !isEndOfDay(task.due_time);
}
