import { Course } from "../grades/types";
import { daysBetween } from "../../shared/utils/dateUtils";

/**
 * Laying a term's courses out on one horizontal axis.
 *
 * Kept out of the component so it can be exercised on its own. Position
 * arithmetic is the kind that goes wrong silently -- a bar an inch off looks
 * like a design choice rather than a bug -- which is the same reason the week
 * view's overlap maths lives in `weekLayout.ts`.
 */

export interface TermSpan {
  starts_on: string;
  ends_on: string;
  days: number;
}

export interface PlacedCourse {
  course: Course;
  /** Percentage from the left edge of the span. */
  left: number;
  /** Percentage of the span's width. */
  width: number;
}

export interface Timeline {
  span: TermSpan | null;
  placed: PlacedCourse[];
  /** Courses in the term carrying no dates, which the chart cannot place. */
  undated: Course[];
  /** Where today sits, as a percentage, or null when it is outside the span. */
  todayAt: number | null;
}

/**
 * The dates a term actually runs, from the courses in it.
 *
 * Earliest start to latest end. A year-long course stretches it, which is
 * correct: that genuinely is how long the term runs for you. Courses with no
 * dates contribute nothing rather than defaulting to today, which would shrink
 * the span to a point.
 */
export function termSpan(courses: Course[]): TermSpan | null {
  const starts = courses.map((c) => c.start_date).filter((d): d is string => !!d);
  const ends = courses.map((c) => c.end_date).filter((d): d is string => !!d);
  if (starts.length === 0 || ends.length === 0) return null;

  const starts_on = starts.reduce((a, b) => (a < b ? a : b));
  const ends_on = ends.reduce((a, b) => (a > b ? a : b));

  return {
    starts_on,
    ends_on,
    // Inclusive, so a term that starts and ends on the same day is one day
    // rather than zero -- and a zero would divide by nothing below.
    days: Math.max(1, daysBetween(starts_on, ends_on) + 1),
  };
}

/**
 * Place each course as a bar across the span.
 *
 * A course missing either date cannot be placed and is reported separately
 * rather than dropped: half the courses in this app carry no dates, and a chart
 * that quietly showed three of six would under-report the term while looking
 * complete.
 */
export function buildTimeline(courses: Course[], today: string): Timeline {
  const span = termSpan(courses);
  if (span === null) {
    return { span: null, placed: [], undated: [...courses], todayAt: null };
  }

  const placed: PlacedCourse[] = [];
  const undated: Course[] = [];

  for (const course of courses) {
    if (!course.start_date || !course.end_date) {
      undated.push(course);
      continue;
    }

    const offset = daysBetween(span.starts_on, course.start_date);
    const length = daysBetween(course.start_date, course.end_date) + 1;

    placed.push({
      course,
      left: (offset / span.days) * 100,
      // A one-day course would otherwise be invisible; a floor keeps every
      // course clickable and countable.
      width: Math.max((length / span.days) * 100, 1.5),
    });
  }

  // Earliest first, then longest, so the shape of the term reads down the page.
  placed.sort((a, b) =>
    a.course.start_date!.localeCompare(b.course.start_date!) || b.width - a.width
  );

  const elapsed = daysBetween(span.starts_on, today);
  const inside = elapsed >= 0 && elapsed <= span.days;

  return {
    span,
    placed,
    undated,
    todayAt: inside ? (elapsed / span.days) * 100 : null,
  };
}
