/** Calendar types; they mirror app/Calendar/schemas/event.py. */

/** What an event is; decides its colour and grouping. */
export type EventKind =
  | "lecture"
  | "lab"
  | "discussion"
  | "midterm"
  | "final"
  | "deadline"
  | "personal"
  | "shift";

/** How often a recurrence repeats. */
export type Frequency = "daily" | "weekly" | "monthly";

/** Two-letter weekday codes, as the API's byday uses them. */
export type Weekday = "MO" | "TU" | "WE" | "TH" | "FR" | "SA" | "SU";

/** Kinds a course timetable is built from. */
export const CLASS_KINDS: EventKind[] = ["lecture", "lab", "discussion"];

/** Kinds the calendar themes as an exam rather than a class. */
export const EXAM_KINDS: EventKind[] = ["midterm", "final"];

/** Display label for each event kind. */
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

/** How an event repeats. */
export interface Recurrence {
  freq: Frequency;
  /** Every N days, weeks or months, per `freq`. */
  interval: number;
  /** Weekly only; empty means the weekday the event starts on. */
  byday: Weekday[];
  /** Inclusive last date; never set alongside `count`. */
  until: string | null;
  /** Number of occurrences; never set alongside `until`. */
  count: number | null;
}

/** One stored event: a single row however often it repeats. */
export interface CalendarEvent {
  id: string;
  title: string;
  kind: EventKind;
  course_id: string | null;
  location: string | null;
  notes: string | null;
  /** First date, YYYY-MM-DD. */
  starts_on: string;
  /** "HH:MM[:SS]"; null together with `end_time` for an all-day event. */
  start_time: string | null;
  end_time: string | null;
  recurrence: Recurrence | null;
  /** Dates the rule generates that have been cancelled. */
  skipped_dates: string[];
}

/** One date an event falls on, built per request, never stored; keyed by `(event_id, on_date)`. */
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
  /** Set on a shift, as `course_id` is on a lecture. */
  job_id: string | null;
  /** True when the event has a repeat rule. */
  repeats: boolean;
  /** Set when a dated grade made this block; the gradebook owns it, so it has no delete here. */
  grade_id: string | null;
  /** Set when someone else shared their event or task date with you; theirs to change. */
  shared?: { owner_name: string; member_names: string[]; what: "event" | "task" };
  /** A job application's deadline or follow-up: an all-day pointer back to the tracker. */
  application?: { id: string; what: "deadline" | "follow_up"; company: string; role: string };
}

/** Request body for creating an event. */
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
  /** Dates the series skips; a break for every class is a `TermBlackout` instead. */
  skipped_dates: string[];
}

/** Patch body for an event. */
export type EventUpdate = Partial<EventCreate>;

/** One recurring block of a course's timetable. */
export interface ClassMeeting {
  kind: EventKind;
  days: Weekday[];
  start_time: string;
  end_time: string;
  location: string | null;
  /** Every N weeks (1 weekly, 2 fortnightly); per meeting, since courses mix them. */
  interval: number;
  /** First date of a non-weekly cycle, e.g. a lab starting in week two; ignored when weekly. */
  first_on: string | null;
}

/** Longest meeting cycle allowed, in weeks. */
export const MAX_MEETING_INTERVAL = 8;

/** Labels for the common meeting intervals, keyed by weeks. */
export const INTERVAL_LABELS: Record<number, string> = {
  1: "Every week",
  2: "Every 2 weeks",
  3: "Every 3 weeks",
  4: "Every 4 weeks",
};

/** Request body building a course's timetable from its weekly meetings. */
export interface ClassScheduleCreate {
  meetings: ClassMeeting[];
  /** Null falls back to the course's own term dates, as does a null `ends_on`. */
  starts_on: string | null;
  ends_on: string | null;
}

/** A gap between commitments long enough to use, inside the study window. */
export interface FreeBlock {
  on_date: string;
  starts_at: string;
  ends_at: string;
  minutes: number;
}

/** A window's load in minutes, with booked events and task estimates kept apart. */
export interface WeekLoad {
  starts_on: string;
  ends_on: string;
  booked_minutes: number;
  /** Task estimates, scaled by `estimate_ratio` when that is set. */
  estimated_minutes: number;
  /** The estimates as typed, before any scaling. */
  typed_estimated_minutes?: number;
  /** Actual over estimated task time, when the forecast applies it. */
  estimate_ratio?: number | null;
  task_count: number;
  unestimated_tasks: number;
  event_count: number;
}

/** One week of the crunch strip. */
export interface CrunchWeek {
  starts_on: string;
  /** Weighted by kind: a final outweighs a midterm outweighs a deadline. */
  weight: number;
  exams: number;
  deadlines: number;
  tasks: number;
  is_current: boolean;
}

/** The coming weeks' crunch, with the peak the bars are scaled against. */
export interface CrunchStrip {
  weeks: CrunchWeek[];
  /** The heaviest week's weight; each bar is a share of it. */
  peak: number;
}

/**
 * A break when classes don't run, cancelling every course-linked recurring event in range.
 * Course events only on purpose: payments and repeating tasks still fall due.
 */
export interface TermBlackout {
  id: string;
  label: string;
  starts_on: string;
  /** Inclusive; equals `starts_on` for a single day. */
  ends_on: string;
  /** Dates covered, counting both ends. */
  days: number;
}

/** Request body for a term blackout. */
export interface TermBlackoutCreate {
  label: string;
  starts_on: string;
  ends_on: string;
}
