import { EventOccurrence } from "./types";
import { Task } from "../tasks/types";
import { hasSpecificTime } from "../tasks/dueTime";
import { minutesOfDay } from "../../shared/utils/dateUtils";

/** Pixels per hour on the week grid; tall enough for a 50-minute class's title. */
export const HOUR_HEIGHT = 46;

/** First hour the grid draws; always the whole day, so an hour sits in one place every week. */
export const DAY_START = 0;
/** Hour the grid ends at, exclusive. */
export const DAY_END = 24;

/** Hour the grid body scrolls to on open. */
export const OPENING_HOUR = 7;

/** Length, in minutes, a block with no end time is drawn as. */
export const ASSUMED_MINUTES = 60;

/** Shortest block drawn, in minutes, so it has room for a title. */
const MINIMUM_MINUTES = 20;

/** Deadlines closer than this many minutes split the width instead of stacking. */
const NEARBY_MINUTES = 30;

/** An event block on the grid: its minutes, and its sub-column within an overlap cluster. */
export interface Placed {
  occurrence: EventOccurrence;
  startMinutes: number;
  endMinutes: number;
  /** Which sub-column of its overlap cluster this sits in. */
  column: number;
  /** How many sub-columns the cluster needs. */
  columns: number;
}

/** Lay a day's timed events out by start time, putting overlapping ones side by side. */
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

/** A timed task marker on the grid, with its sub-column among nearby deadlines. */
export interface PlacedTask {
  task: Task;
  minutes: number;
  /** Which sub-column of its cluster of simultaneous deadlines this sits in. */
  column: number;
  /** How many sub-columns that cluster needs. */
  columns: number;
}

/**
 * Place a day's timed tasks as markers at their due minute; ones within `NEARBY_MINUTES` share.
 * Takes only `hasSpecificTime` tasks, the ones the all-day band leaves out.
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

/** Every hour the grid draws, from `DAY_START` up to `DAY_END`. */
export const HOURS = Array.from(
  { length: DAY_END - DAY_START },
  (_, index) => DAY_START + index
);
