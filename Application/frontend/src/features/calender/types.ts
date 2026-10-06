/** Mirrors app/Calendar/schemas/event.py. */

export type EventKind =
  | "lecture"
  | "lab"
  | "discussion"
  | "midterm"
  | "final"
  | "deadline"
  | "personal"
  | "shift";

export type Frequency = "daily" | "weekly" | "monthly";

export type Weekday = "MO" | "TU" | "WE" | "TH" | "FR" | "SA" | "SU";

/** The kinds a course timetable is built from. */
export const CLASS_KINDS: EventKind[] = ["lecture", "lab", "discussion"];

/** The kinds the calendar themes as an exam rather than a class. */
export const EXAM_KINDS: EventKind[] = ["midterm", "final"];

export const EVENT_KIND_LABELS: Record<EventKind, string> = {
  lecture: "Lecture",
  lab: "Lab",
  discussion: "Discussion",
  midterm: "Midterm",
  final: "Final",
  deadline: "Deadline",
  personal: "Personal",
  shift: "Shift",
};

export interface Recurrence {
  freq: Frequency;
  /** Every N days/weeks/months. */
  interval: number;
  /** Weekly only. Empty means the weekday the event starts on. */
  byday: Weekday[];
  /** Inclusive last date. Never set alongside `count`. */
  until: string | null;
  count: number | null;
}

/** One stored event -- one row, however often it repeats. */
export interface CalendarEvent {
  id: string;
  title: string;
  kind: EventKind;
  course_id: string | null;
  location: string | null;
  notes: string | null;
  starts_on: string;
  /** Both null means an all-day event. */
  start_time: string | null;
  end_time: string | null;
  recurrence: Recurrence | null;
  /** Dates the rule generates that have been cancelled. */
  skipped_dates: string[];
}

/**
 * One date a series actually falls on.
 *
 * Materialised by the API per request and never stored, so it has no id of its
 * own: `(event_id, on_date)` is what identifies it.
 */
export interface EventOccurrence {
  event_id: string;
  on_date: string;
  title: string;
  kind: EventKind;
  start_time: string | null;
  end_time: string | null;
  location: string | null;
  notes: string | null;
  course_id: string | null;
  course_code: string | null;
  /** Set on a shift, the way course_id is set on a lecture. */
  job_id: string | null;
  repeats: boolean;
  /**
   * Set when a dated grade produced this block. The gradebook owns it, so there
   * is no delete here — removing it would only bring it back the next time the
   * grade was saved.
   */
  grade_id: string | null;
}

export interface EventCreate {
  title: string;
  kind: EventKind;
  course_id: string | null;
  location: string | null;
  notes: string | null;
  starts_on: string;
  start_time: string | null;
  end_time: string | null;
  recurrence: Recurrence | null;
  /**
   * Dates this series does not run — a cancelled lecture, a week away.
   *
   * Set while editing, rather than only by skipping occurrences after the fact.
   * A reading break that applies to every class is a TermBlackout instead.
   */
  skipped_dates: string[];
}

export type EventUpdate = Partial<EventCreate>;

/** One recurring block of a course's timetable. */
export interface ClassMeeting {
  kind: EventKind;
  days: Weekday[];
  start_time: string;
  end_time: string;
  location: string | null;
  /**
   * Every N weeks. 1 is weekly, 2 is fortnightly.
   *
   * On the meeting rather than the schedule, because a course routinely mixes
   * them: a weekly lecture beside a fortnightly lab is the ordinary case.
   */
  interval: number;
  /**
   * Which week the cycle starts on, for anything that is not weekly.
   *
   * Without it every fortnightly meeting is pinned to the odd weeks of term,
   * because the whole timetable shares one start date — and labs commonly begin
   * in week two. Ignored when the interval is 1.
   */
  first_on: string | null;
}

/** Weekly through every eight weeks. Past that it is a mistake, not a schedule. */
export const MAX_MEETING_INTERVAL = 8;

export const INTERVAL_LABELS: Record<number, string> = {
  1: "Every week",
  2: "Every 2 weeks",
  3: "Every 3 weeks",
  4: "Every 4 weeks",
};

export interface ClassScheduleCreate {
  meetings: ClassMeeting[];
  /** Null falls back to the course's own term dates. */
  starts_on: string | null;
  ends_on: string | null;
}

/** A gap between commitments long enough to be worth putting something in. */
export interface FreeBlock {
  on_date: string;
  starts_at: string;
  ends_at: string;
  minutes: number;
}

/**
 * What a window costs, in hours rather than item counts.
 *
 * Booked and estimated stay apart: booked time is not optional, estimated time
 * is a guess you wrote down, and one combined number would hide which half is
 * which — and hide that most tasks carry no estimate at all.
 */
export interface WeekLoad {
  starts_on: string;
  ends_on: string;
  booked_minutes: number;
  /** Scaled by `estimate_ratio` when that is set. */
  estimated_minutes: number;
  /** The estimates as typed, before any scaling. */
  typed_estimated_minutes?: number;
  /** How long tasks really take against their estimates, when the forecast uses it. */
  estimate_ratio?: number | null;
  task_count: number;
  unestimated_tasks: number;
  event_count: number;
}

export interface CrunchWeek {
  starts_on: string;
  /** Weighted by kind: a final outweighs a midterm outweighs a deadline. */
  weight: number;
  exams: number;
  deadlines: number;
  tasks: number;
  is_current: boolean;
}

export interface CrunchStrip {
  weeks: CrunchWeek[];
  /** The heaviest week, so a bar is a share of the worst week rather than a guess. */
  peak: number;
}

/**
 * A stretch of term when classes do not run.
 *
 * Set once and subtracted from every recurring event that belongs to a course,
 * because one reading break applies to all six of your classes. Scoped to
 * course-linked events on purpose: the same recurrence engine drives recurring
 * payments and repeating tasks, and rent is still due during reading break.
 */
export interface TermBlackout {
  id: string;
  label: string;
  starts_on: string;
  /** Inclusive, and equal to starts_on for a single day. */
  ends_on: string;
  days: number;
}

export interface TermBlackoutCreate {
  label: string;
  starts_on: string;
  ends_on: string;
}
