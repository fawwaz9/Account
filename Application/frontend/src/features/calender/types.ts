/** Mirrors app/Calendar/schemas/event.py. */

export type EventKind =
  | "lecture"
  | "lab"
  | "discussion"
  | "midterm"
  | "final"
  | "deadline"
  | "personal";

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
}

export type EventUpdate = Partial<EventCreate>;

/** One recurring block of a course's timetable. */
export interface ClassMeeting {
  kind: EventKind;
  days: Weekday[];
  start_time: string;
  end_time: string;
  location: string | null;
}

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
  estimated_minutes: number;
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
