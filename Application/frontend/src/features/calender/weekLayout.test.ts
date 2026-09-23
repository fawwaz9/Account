import { describe, expect, it } from "vitest";
import { ASSUMED_MINUTES, place, placeTasks } from "./weekLayout";
import type { EventOccurrence } from "./types";
import type { Task } from "../tasks/types";

/**
 * The week view's overlap arithmetic, which until now was checked only by
 * one-off esbuild harnesses that ran when someone remembered to write one.
 *
 * It is worth pinning because its failure is silent: two classes at the same
 * hour drawn on top of each other look like one class, and the week view exists
 * to prevent exactly that.
 */
function at(start: string | null, end: string | null, title = "x"): EventOccurrence {
  return { title, start_time: start, end_time: end } as EventOccurrence;
}

function due(due_time: string | null, title = "x"): Task {
  return { title, due_time } as Task;
}

describe("place", () => {
  it("leaves an untimed occurrence out, for the all-day band to draw", () => {
    expect(place([at(null, null)])).toHaveLength(0);
  });

  it("gives a lone event the full width", () => {
    const [block] = place([at("09:00", "10:00")]);

    expect(block.startMinutes).toBe(540);
    expect(block.endMinutes).toBe(600);
    expect(block.column).toBe(0);
    expect(block.columns).toBe(1);
  });

  it("puts two events at the same hour side by side", () => {
    const placed = place([at("09:00", "10:00", "a"), at("09:00", "10:00", "b")]);

    expect(placed.map((p) => p.column)).toEqual([0, 1]);
    expect(placed.every((p) => p.columns === 2)).toBe(true);
  });

  it("widens a cluster to its busiest moment", () => {
    const placed = place([
      at("09:00", "12:00", "a"),
      at("09:30", "10:30", "b"),
      at("10:00", "11:00", "c"),
    ]);

    expect(placed.every((p) => p.columns === 3)).toBe(true);
    expect(placed.map((p) => p.column)).toEqual([0, 1, 2]);
  });

  it("keeps separate clusters at full width apiece", () => {
    const placed = place([at("09:00", "10:00", "a"), at("11:00", "12:00", "b")]);

    expect(placed.every((p) => p.columns === 1)).toBe(true);
    expect(placed.every((p) => p.column === 0)).toBe(true);
  });

  /**
   * Touching is not overlapping. A 10:00 class begins exactly where the 09:00
   * one ends, so it takes the full width rather than half of it -- otherwise a
   * day of back-to-back lectures would draw every one at half width for no
   * reason.
   */
  it("treats an event starting as another ends as not overlapping", () => {
    const placed = place([at("09:00", "10:00", "a"), at("10:00", "11:00", "b")]);

    expect(placed.every((p) => p.columns === 1)).toBe(true);
  });

  it("reuses a column once its previous event has ended", () => {
    // b and c both overlap the long a, but never each other, so the cluster is
    // two wide rather than three and c takes back the column b finished with.
    // Note the sort runs first: b is shorter, so it takes column 0 and the
    // three-hour a is pushed to column 1.
    const placed = place([
      at("09:00", "12:00", "a"),
      at("09:00", "10:00", "b"),
      at("10:00", "11:00", "c"),
    ]);
    const byTitle = Object.fromEntries(placed.map((p) => [p.occurrence.title, p]));

    expect(byTitle.b.column).toBe(0);
    expect(byTitle.a.column).toBe(1);
    expect(byTitle.c.column).toBe(byTitle.b.column);
    expect(placed.every((p) => p.columns === 2)).toBe(true);
  });

  it("gives an event with no end time an assumed height", () => {
    const [block] = place([at("09:00", null)]);

    expect(block.endMinutes - block.startMinutes).toBe(ASSUMED_MINUTES);
  });

  /**
   * A block that ends the minute it starts would be a zero-height strip: not
   * readable, and not clickable either.
   */
  it("floors a zero-length block to something clickable", () => {
    const [block] = place([at("09:00", "09:00")]);

    expect(block.endMinutes - block.startMinutes).toBeGreaterThanOrEqual(20);
  });

  it("orders by start, then by end", () => {
    const placed = place([
      at("11:00", "12:00", "late"),
      at("09:00", "11:00", "long"),
      at("09:00", "10:00", "short"),
    ]);

    expect(placed.map((p) => p.occurrence.title)).toEqual(["short", "long", "late"]);
  });
});

describe("placeTasks", () => {
  /**
   * The complementarity rule, and the reason it is a test rather than a
   * comment: the grid draws the tasks `hasSpecificTime` is true of and the
   * all-day band draws the rest. If these two ever disagree a task shows up
   * twice, or vanishes.
   */
  it("leaves out a task with no time, and one due at end of day", () => {
    expect(placeTasks([due(null), due("23:59"), due("23:59:00")])).toHaveLength(0);
  });

  it("puts a timed task on the clock", () => {
    const [marker] = placeTasks([due("14:30")]);

    expect(marker.minutes).toBe(870);
    expect(marker.column).toBe(0);
    expect(marker.columns).toBe(1);
  });

  it("splits the width between deadlines close together", () => {
    const placed = placeTasks([due("09:00", "a"), due("09:20", "b")]);

    expect(placed.map((p) => p.column)).toEqual([0, 1]);
    expect(placed.every((p) => p.columns === 2)).toBe(true);
  });

  it("starts a new cluster once a deadline is far enough from the first", () => {
    const placed = placeTasks([due("09:00", "a"), due("09:20", "b"), due("09:45", "c")]);
    const byTitle = Object.fromEntries(placed.map((p) => [p.task.title, p]));

    expect(byTitle.a.columns).toBe(2);
    expect(byTitle.b.columns).toBe(2);
    expect(byTitle.c.columns).toBe(1);
    expect(byTitle.c.column).toBe(0);
  });

  it("sorts by time regardless of the order given", () => {
    const placed = placeTasks([due("16:00", "late"), due("08:00", "early")]);

    expect(placed.map((p) => p.task.title)).toEqual(["early", "late"]);
  });
});
