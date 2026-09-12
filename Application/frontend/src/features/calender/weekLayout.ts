import { EventOccurrence } from "./types";
import { Task } from "../tasks/types";
import { hasSpecificTime } from "../tasks/dueTime";
import { minutesOfDay } from "../../shared/utils/dateUtils";

/** Pixels per hour. Tall enough that a 50-minute class can show its title. */
export const HOUR_HEIGHT = 46;

/**
 * The whole day, always.
 *
 * This used to draw 8am–9pm and widen only to fit outlying events, which keeps
 * the grid short but means the hours on screen change as the week's contents
 * change — so the same 9am sat in a different place from one week to the next.
 * A fixed 24 hours in a scrolling body is steadier, and nothing can be clipped.
 */
export const DAY_START = 0;
export const DAY_END = 24;

/** Where the body is scrolled to on open: early enough to catch a 8am lecture. */
export const OPENING_HOUR = 7;

/** How long a block with no end time is drawn as. */
export const ASSUMED_MINUTES = 60;

/** Shortest block that still has room for a title. */
const MINIMUM_MINUTES = 20;

/** Deadlines closer together than this are drawn side by side, not stacked. */
const NEARBY_MINUTES = 30;

export interface Placed {
  occurrence: EventOccurrence;
  startMinutes: number;
  endMinutes: number;
  /** Which sub-column of its overlap cluster this sits in. */
  column: number;
  /** How many sub-columns the cluster needs. */
  columns: number;
}

/**
 * Lay a day's timed events out, putting anything that overlaps side by side.
 *
 * Without this, two classes at the same hour draw on top of each other and one
 * is simply invisible — which is the single thing a week view exists to
 * prevent. Events are grouped into clusters of mutual overlap, and each cluster
 * is divided into as many columns as its busiest moment needs.
 *
 * Kept out of the component so it can be exercised on its own: it is the part
 * of a week view that goes wrong silently.
 */
export function place(occurrences: EventOccurrence[]): Placed[] {
  const timed = occurrences
    .map((occurrence) => {
      const start = minutesOfDay(occurrence.start_time);
      if (start === null) return null;
      const end = minutesOfDay(occurrence.end_time);
      return {
        occurrence,
        startMinutes: start,
        // A block with no end still needs a height, and one that ends the
        // minute it starts needs enough room to be clickable.
        endMinutes: Math.max(end ?? start + ASSUMED_MINUTES, start + MINIMUM_MINUTES),
      };
    })
    .filter((item): item is Omit<Placed, "column" | "columns"> => item !== null)
    .sort((a, b) => a.startMinutes - b.startMinutes || a.endMinutes - b.endMinutes);

  const placed: Placed[] = [];
  let cluster: Placed[] = [];
  let clusterEnd = -1;

  function closeCluster() {
    const width = cluster.reduce((widest, item) => Math.max(widest, item.column + 1), 0);
    for (const item of cluster) item.columns = width;
    cluster = [];
    clusterEnd = -1;
  }

  for (const item of timed) {
    // A gap means nothing after this point can overlap anything before it, so
    // the cluster is finished and its width is finally known.
    if (item.startMinutes >= clusterEnd) closeCluster();

    // The first column whose previous event has already ended.
    const taken = new Set(
      cluster
        .filter((other) => other.endMinutes > item.startMinutes)
        .map((other) => other.column)
    );
    let column = 0;
    while (taken.has(column)) column += 1;

    const entry: Placed = { ...item, column, columns: 1 };
    cluster.push(entry);
    placed.push(entry);
    clusterEnd = Math.max(clusterEnd, item.endMinutes);
  }
  closeCluster();

  return placed;
}

export interface PlacedTask {
  task: Task;
  minutes: number;
  /** Which sub-column of its cluster of simultaneous deadlines this sits in. */
  column: number;
  /** How many sub-columns that cluster needs. */
  columns: number;
}

/**
 * Put a day's timed tasks on the clock.
 *
 * Deliberately not `place`. An event occupies a span and is drawn as a box with
 * a height; a task is due *at* a moment and has no duration at all, so giving it
 * one would draw an hour of work that was never claimed. These are markers on
 * the time axis, and they are laid out separately so they can sit above the
 * blocks rather than fight them for a column.
 *
 * Deadlines within `NEARBY_MINUTES` of each other share a cluster and split the
 * width, so two things due at the same hour stay legible instead of stacking
 * exactly on top of one another.
 *
 * Takes only the tasks `hasSpecificTime` is true of, which is exactly what the
 * all-day band leaves out. The two must stay complementary or a task shows
 * twice or not at all.
 */
export function placeTasks(tasks: Task[]): PlacedTask[] {
  const timed = tasks
    .filter(hasSpecificTime)
    .map((task) => {
      const minutes = minutesOfDay(task.due_time);
      return minutes === null ? null : { task, minutes };
    })
    .filter((item): item is { task: Task; minutes: number } => item !== null)
    .sort((a, b) => a.minutes - b.minutes);

  const placed: PlacedTask[] = [];
  let cluster: PlacedTask[] = [];

  function closeCluster() {
    for (const item of cluster) item.columns = cluster.length;
    cluster = [];
  }

  for (const item of timed) {
    if (cluster.length > 0 && item.minutes - cluster[0].minutes >= NEARBY_MINUTES) {
      closeCluster();
    }

    const entry: PlacedTask = { ...item, column: cluster.length, columns: 1 };
    cluster.push(entry);
    placed.push(entry);
  }
  closeCluster();

  return placed;
}

/** The hours the grid draws, as a list. */
export const HOURS = Array.from(
  { length: DAY_END - DAY_START },
  (_, index) => DAY_START + index
);
