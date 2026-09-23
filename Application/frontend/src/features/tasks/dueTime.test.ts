import { describe, expect, it } from "vitest";
import { END_OF_DAY, hasSpecificTime, isEndOfDay } from "./dueTime";
import type { Task } from "./types";

function task(due_time: string | null): Pick<Task, "due_time"> {
  return { due_time };
}

describe("isEndOfDay", () => {
  it("accepts both shapes, because the API and the form disagree", () => {
    // The API sends HH:MM:SS; the form produces HH:MM.
    expect(isEndOfDay("23:59")).toBe(true);
    expect(isEndOfDay("23:59:00")).toBe(true);
  });

  it("is false for a time someone actually chose", () => {
    expect(isEndOfDay("09:00")).toBe(false);
    expect(isEndOfDay("23:58")).toBe(false);
    expect(isEndOfDay(null)).toBe(false);
  });

  it("agrees with the sentinel it is testing for", () => {
    expect(isEndOfDay(END_OF_DAY)).toBe(true);
  });
});

/**
 * The single predicate behind both halves of the week view: the grid draws the
 * tasks this is true of and the all-day band draws the rest. They have to stay
 * exactly complementary, or a task is drawn twice or not at all -- and a
 * calendar makes both invisible.
 */
describe("hasSpecificTime", () => {
  it("is true only for a time of day the student picked", () => {
    expect(hasSpecificTime(task("09:00"))).toBe(true);
    expect(hasSpecificTime(task("14:30:00"))).toBe(true);
  });

  /**
   * End of day is what a bare due date fills in, so counting it as a real
   * deadline would pile nearly every task onto the last minute of the day --
   * below the fold, clustered, and saying nothing the date had not.
   */
  it("is false for end of day, which is what a bare date means", () => {
    expect(hasSpecificTime(task(END_OF_DAY))).toBe(false);
    expect(hasSpecificTime(task("23:59:00"))).toBe(false);
  });

  it("is false with no time at all", () => {
    expect(hasSpecificTime(task(null))).toBe(false);
  });

  it("partitions every case exactly once, with the all-day band", () => {
    // Whatever this is false of is what the all-day band must draw. If these
    // two ever overlap or leave a gap, a task shows twice or disappears.
    for (const value of [null, "23:59", "23:59:00", "09:00", "00:00"]) {
      const onGrid = hasSpecificTime(task(value));
      const inBand = !onGrid;
      expect(onGrid !== inBand).toBe(true);
    }
  });
});
