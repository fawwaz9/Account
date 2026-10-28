import { END_OF_DAY } from "./dueTime";

/** Field rules shared by the inline add row and the edit dialog, so the two forms can't drift. */

/** A form's due date and time. */
export interface Deadline {
  due_date: string | null;
  due_time: string | null;
}

/**
 * Set the due date: clearing it clears the time, and a new date with no time gets `END_OF_DAY`.
 * The API refuses a time of day without a date.
 */
export function withDueDate<T extends Deadline>(current: T, value: string | null): T {
  return {
    ...current,
    due_date: value,
    due_time: value === null ? null : current.due_time ?? END_OF_DAY,
  };
}

/** Split comma-separated text into trimmed tags, dropping blanks. */
export function parseTags(text: string): string[] {
  return text.split(",").map((tag) => tag.trim()).filter(Boolean);
}

/** Join tags back into the text box's comma-separated form. */
export function tagText(tags: readonly string[]): string {
  return tags.join(", ");
}

/** A number box's value, or null when it is empty, since `Number` reads "" as 0. */
export function numberOrNull(value: string): number | null {
  return value === "" ? null : Number(value);
}
