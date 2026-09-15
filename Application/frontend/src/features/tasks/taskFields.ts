import { END_OF_DAY } from "./dueTime";

/**
 * The rules a task form has to follow, in one place.
 *
 * Both of these exist in two forms now -- the inline add row on the task page
 * and the edit dialog opened from a row or a calendar chip -- and both fail
 * silently when they drift: one produces a save the API rejects, the other
 * quietly drops what was typed.
 */

/** The shape both forms hold a deadline in. */
export interface Deadline {
  due_date: string | null;
  due_time: string | null;
}

/**
 * Set the date, keeping the time honest.
 *
 * The two move together. A time of day with no date is refused by the API --
 * "A time of day needs a date to go with it" -- so clearing the date has to
 * clear the time. Setting one pre-fills the end of that day, because a deadline
 * with no time really is "by the end of Friday", and `hasSpecificTime` reads
 * 23:59 back as no particular time so nothing renders it as a real deadline.
 */
export function withDueDate<T extends Deadline>(current: T, value: string | null): T {
  return {
    ...current,
    due_date: value,
    due_time: value === null ? null : current.due_time ?? END_OF_DAY,
  };
}

/**
 * "reading, cpsc 221 , ,lab" -> ["reading", "cpsc 221", "lab"].
 *
 * Blanks dropped rather than stored: a trailing comma is how anyone types a
 * list, and an empty tag renders as a stray chip nothing can remove.
 */
export function parseTags(text: string): string[] {
  return text.split(",").map((tag) => tag.trim()).filter(Boolean);
}

/** The reverse, for loading an existing task back into a text box. */
export function tagText(tags: readonly string[]): string {
  return tags.join(", ");
}

/**
 * What a number box means when it is empty.
 *
 * `Number("")` is 0, so reading the box directly records "takes no time"
 * where the student meant "no estimate given" -- and a 0-minute estimate is
 * counted in the week's hours as a task that costs nothing.
 */
export function numberOrNull(value: string): number | null {
  return value === "" ? null : Number(value);
}
