import { EventOccurrence } from "./types";
import { minutesOfDay } from "../../shared/utils/dateUtils";

/** Pixels per hour. Tall enough that a 50-minute class can show its title. */
export const HOUR_HEIGHT = 46;

/** The hours always drawn, whether or not anything is in them. */
export const DEFAULT_START_HOUR = 8;
export const DEFAULT_END_HOUR = 21;

/** How long a block with no end time is drawn as. */
export const ASSUMED_MINUTES = 60;

/** Shortest block that still has room for a title. */
const MINIMUM_MINUTES = 20;

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

/** The hour range to draw: the usual day, widened to fit anything outside it. */
export function hourRange(
  days: { occurrences: EventOccurrence[] }[]
): [number, number] {
  let start = DEFAULT_START_HOUR;
  let end = DEFAULT_END_HOUR;

  for (const day of days) {
    for (const occurrence of day.occurrences) {
      const from = minutesOfDay(occurrence.start_time);
      if (from === null) continue;
      const to = minutesOfDay(occurrence.end_time) ?? from + ASSUMED_MINUTES;
      start = Math.min(start, Math.floor(from / 60));
      end = Math.max(end, Math.ceil(to / 60));
    }
  }

  return [start, Math.max(end, start + 1)];
}
