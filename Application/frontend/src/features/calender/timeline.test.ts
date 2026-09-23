import { describe, expect, it } from "vitest";
import { buildTimeline, termSpan } from "./timeline";
import type { Course } from "../grades/types";

/**
 * Position arithmetic, kept out of the component precisely so it can be
 * exercised here: a bar an inch off reads as a design choice rather than a bug,
 * so nothing about the page would report this going wrong.
 */
function course(code: string, start_date: string | null, end_date: string | null): Course {
  return { code, name: code, start_date, end_date } as Course;
}

describe("termSpan", () => {
  it("is null when nothing carries dates", () => {
    expect(termSpan([course("A", null, null)])).toBeNull();
    expect(termSpan([])).toBeNull();
  });

  it("runs from the earliest start to the latest end", () => {
    const span = termSpan([
      course("A", "2026-09-08", "2026-12-04"),
      course("B", "2026-09-01", "2026-11-30"),
    ]);

    expect(span?.starts_on).toBe("2026-09-01");
    expect(span?.ends_on).toBe("2026-12-04");
  });

  /**
   * Inclusive, and the floor of 1 is load-bearing rather than tidy: `days` is
   * the denominator every bar is placed against, so a term that starts and ends
   * on one day would otherwise divide by zero and every position would be NaN.
   */
  it("counts a single-day term as one day, not zero", () => {
    expect(termSpan([course("A", "2026-09-01", "2026-09-01")])?.days).toBe(1);
  });

  it("counts inclusively", () => {
    expect(termSpan([course("A", "2026-09-01", "2026-09-10")])?.days).toBe(10);
  });

  it("ignores a course missing one of its two dates", () => {
    const span = termSpan([
      course("A", "2026-09-01", "2026-09-10"),
      course("B", "2026-08-01", null),
    ]);

    // B's start is earlier, but with no end it cannot define a span.
    expect(span?.starts_on).toBe("2026-08-01");
    expect(span?.ends_on).toBe("2026-09-10");
  });
});

describe("buildTimeline", () => {
  it("reports every course as undated when the term has no span", () => {
    const timeline = buildTimeline([course("A", null, null)], "2026-09-15");

    expect(timeline.span).toBeNull();
    expect(timeline.placed).toHaveLength(0);
    expect(timeline.undated.map((c) => c.code)).toEqual(["A"]);
    expect(timeline.todayAt).toBeNull();
  });

  /**
   * Half the courses in this app carry no dates, so a chart quietly showing
   * three of six would under-report the term while looking complete.
   */
  it("names an undated course rather than dropping it", () => {
    const timeline = buildTimeline(
      [course("A", "2026-09-01", "2026-12-01"), course("B", null, null)],
      "2026-09-15"
    );

    expect(timeline.placed.map((p) => p.course.code)).toEqual(["A"]);
    expect(timeline.undated.map((c) => c.code)).toEqual(["B"]);
  });

  it("places a course filling the whole term across the whole axis", () => {
    const timeline = buildTimeline([course("A", "2026-09-01", "2026-09-10")], "2026-09-05");

    expect(timeline.placed[0].left).toBe(0);
    expect(timeline.placed[0].width).toBe(100);
  });

  it("offsets a course that starts later", () => {
    const timeline = buildTimeline(
      [course("A", "2026-09-01", "2026-09-10"), course("B", "2026-09-06", "2026-09-10")],
      "2026-09-05"
    );
    const b = timeline.placed.find((p) => p.course.code === "B")!;

    expect(b.left).toBe(50);
    expect(b.width).toBe(50);
  });

  it("reads earliest first, then longest", () => {
    const timeline = buildTimeline(
      [
        course("late", "2026-10-01", "2026-10-10"),
        course("short", "2026-09-01", "2026-09-05"),
        course("long", "2026-09-01", "2026-09-20"),
      ],
      "2026-09-15"
    );

    expect(timeline.placed.map((p) => p.course.code)).toEqual(["long", "short", "late"]);
  });

  it("keeps a one-day course visible rather than letting it vanish", () => {
    const timeline = buildTimeline(
      [course("A", "2026-09-01", "2026-12-01"), course("B", "2026-10-01", "2026-10-01")],
      "2026-09-15"
    );
    const b = timeline.placed.find((p) => p.course.code === "B")!;

    expect(b.width).toBeGreaterThanOrEqual(1.5);
  });

  describe("today", () => {
    it("sits proportionally inside the span", () => {
      const timeline = buildTimeline([course("A", "2026-09-01", "2026-09-10")], "2026-09-06");

      expect(timeline.todayAt).toBe(50);
    });

    it("is null before the term and after it", () => {
      const before = buildTimeline([course("A", "2026-09-01", "2026-09-10")], "2026-08-01");
      const after = buildTimeline([course("A", "2026-09-01", "2026-09-10")], "2026-11-01");

      expect(before.todayAt).toBeNull();
      expect(after.todayAt).toBeNull();
    });
  });

  /**
   * The claim the design note makes about this module, checked rather than
   * trusted: no bar is laid outside the axis it is drawn on.
   */
  it("lays no bar outside the axis", () => {
    const timeline = buildTimeline(
      [
        course("A", "2026-09-01", "2026-12-09"),
        course("B", "2026-12-09", "2026-12-09"),
        course("C", "2026-09-01", "2026-09-01"),
      ],
      "2026-10-01"
    );

    for (const bar of timeline.placed) {
      expect(bar.left).toBeGreaterThanOrEqual(0);
      expect(bar.left + bar.width).toBeLessThanOrEqual(100);
    }
  });
});
