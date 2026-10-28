import { Course } from "../grades/types";
import { daysBetween } from "../../shared/utils/dateUtils";

/** Term timeline layout, kept pure for testing: each course as a bar across its term's span. */

/** First and last dates a term's courses cover, and the inclusive day count. */
export interface TermSpan {
  starts_on: string;
  ends_on: string;
  days: number;
}

/** A course's bar, placed as percentages of the span. */
export interface PlacedCourse {
  course: Course;
  /** Percentage from the left edge of the span. */
  left: number;
  /** Percentage of the span's width. */
  width: number;
}

/** A term laid out: its span, the placed bars, the undated courses and today's position. */
export interface Timeline {
  span: TermSpan | null;
  placed: PlacedCourse[];
  /** Courses in the term carrying no dates, which the chart cannot place. */
  undated: Course[];
  /** Where today sits, as a percentage, or null when it is outside the span. */
  todayAt: number | null;
}

/** Earliest start to latest end across the courses' dates; null when either side has none. */
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
 * Lay courses out as bars across their term's span, earliest first, then longest.
 * A course missing a date is listed as undated rather than dropped.
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

    // A one-day course would otherwise be invisible; a floor keeps every
    // course clickable and countable.
    const width = Math.max((length / span.days) * 100, 1.5);

    placed.push({
      course,
      // Slid back where the floor above would otherwise hang the bar off the
      // end: a one-day course on the last day of a hundred-day term is laid at
      // 99% and then widened to 1.5%, which paints half a percent past an axis
      // that nothing clips -- reading as a course running past the end of term.
      // Moving it is the lesser distortion, because the bar is already wider
      // than the day it represents.
      left: Math.max(0, Math.min((offset / span.days) * 100, 100 - width)),
      width,
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
