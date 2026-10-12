import { describe, expect, it } from "vitest";
import { countWeek } from "./useTimeGlance";
import { EventOccurrence } from "../types";

/** The phone dashboard's "2 exams, 3 shifts", counted off the week's calendar. */

function occurrence(kind: EventOccurrence["kind"], id: string): EventOccurrence {
  return {
    event_id: id, on_date: "2026-10-14", title: id, kind, start_time: null, end_time: null,
    location: null, notes: null, course_id: null, course_code: null, job_id: null, repeats: false, grade_id: null,
  };
}

describe("counting the week", () => {
  it("counts midterms and finals as exams, and nothing else", () => {
    const week = [occurrence("midterm", "a"), occurrence("final", "b"), occurrence("lecture", "c"),
      occurrence("deadline", "d")];
    expect(countWeek(week).exams).toBe(2);
  });

  it("counts shifts", () => {
    const week = [occurrence("shift", "a"), occurrence("shift", "b"), occurrence("lab", "c")];
    expect(countWeek(week).shifts).toBe(2);
  });

  it("counts each occurrence of a repeat, since each is a separate day", () => {
    const week = [occurrence("shift", "a"), { ...occurrence("shift", "a"), on_date: "2026-10-15" }];
    expect(countWeek(week).shifts).toBe(2);
  });

  it("is zero for an empty week", () => {
    expect(countWeek([])).toEqual({ exams: 0, shifts: 0 });
  });
});
