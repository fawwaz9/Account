// One repeat rule serves class times, standing payments and repeating chores
// alike, so it is defined once in the calendar feature.
import { Recurrence } from "../calender/types";

/** Mirrors app/Tasks/schemas/task.py. */

export interface Task {
  id: string;
  title: string;
  notes: string | null;
  /** Null for a task with no deadline; one with a date also draws on the calendar. */
  due_date: string | null;
  due_time: string | null;
  /** What you think it will take, so a week's load reads as hours. */
  estimated_minutes: number | null;
  course_id: string | null;
  /** Denormalised by the API. Coursework is categorised by this, not by a tag. */
  course_code: string | null;
  tags: string[];
  done: boolean;
  completed_at: string | null;
  archived: boolean;
  created_at: string | null;
  /**
   * Set when the task was raised from a dated grade. It closes itself when the
   * score lands, so the client does not offer to delete it separately.
   */
  grade_id: string | null;
  /**
   * How far behind the course this task belongs to is, or null when there is
   * nothing to flag. Computed by the API: the client would otherwise need every
   * course, every target and the current-term rule just to colour one row.
   */
  risk: RiskBand | null;
}

/** How far below its target a course has fallen, in percentage points. */
export type RiskBand = "mild" | "moderate" | "severe";

/** Mirrors app/Tasks/schemas/timing.py. */
export interface TimingWindow {
  label: string;
  starts_on: string;
  ends_on: string;
  /** Completed tasks that carried a due date; undated work is excluded. */
  counted: number;
  /** Signed days from the due date: positive late, negative early. */
  mean_days: number | null;
  on_time_percent: number | null;
  early_count: number;
  /** Days early, positive, across the early ones only. */
  early_mean_days: number | null;
  late_count: number;
  /** Days late, positive, across the late ones only. */
  late_mean_days: number | null;
}

export interface CompletionTiming {
  past_week: TimingWindow;
  this_month: TimingWindow;
  /** Completed but undated, so counted by no figure above. */
  undated_completed: number;
}

export interface TaskCreate {
  title: string;
  notes: string | null;
  due_date: string | null;
  due_time: string | null;
  estimated_minutes: number | null;
  course_id: string | null;
  tags: string[];
}

export type TaskUpdate = Partial<TaskCreate> & {
  done?: boolean;
  archived?: boolean;
};

/* ===== Repeating tasks ===== */

/**
 * A chore that comes back: readings every Monday, laundry every fortnight.
 *
 * Stores the rule and a template. Unlike a class time, its occurrences are real
 * task rows, because each is ticked off separately — this week's reading being
 * done says nothing about next week's. Unlike a standing payment, occurrences a
 * little way ahead are written too: a future task costs nothing to have sitting
 * there, and seeing Monday's reading on Sunday is the point.
 */
export interface RecurringTask {
  id: string;
  title: string;
  notes: string | null;
  due_time: string | null;
  estimated_minutes: number | null;
  course_id: string | null;
  course_code: string | null;
  tags: string[];
  starts_on: string;
  recurrence: Recurrence;
  active: boolean;
  skipped_dates: string[];
  created_at: string | null;
  /** The next occurrence still outstanding, or null once the rule has run out. */
  next_due_on: string | null;
}

export interface RecurringTaskCreate {
  title: string;
  notes: string | null;
  due_time: string | null;
  estimated_minutes: number | null;
  course_id: string | null;
  tags: string[];
  starts_on: string;
  recurrence: Recurrence;
  active: boolean;
}

export type RecurringTaskUpdate = Partial<RecurringTaskCreate>;

/** What materialising the window actually created. */
export interface RecurringTaskRun {
  created: number;
  tasks: Task[];
}

/* ===== Quick capture ===== */

/**
 * What one typed line was understood to mean, before anything is written.
 *
 * Read as the student types, so the guess is visible while it is still cheap to
 * reword. A capture box that files things silently is worse than a form,
 * because nothing on screen says what it did.
 */
export interface QuickCapturePreview {
  text: string;
  title: string;
  due_date: string | null;
  estimated_minutes: number | null;
  course_id: string | null;
  course_code: string | null;
  /**
   * A code was typed but matches no course of yours, or matches several. It
   * stays in the title rather than being swallowed.
   */
  unmatched_course: string | null;
  /** Which kinds parsed: course, date, duration, amount, score. */
  matched: string[];
  /** False when there is nothing left to make a task from. */
  can_create: boolean;
}

export interface QuickCaptureResult {
  task: Task;
  preview: QuickCapturePreview;
}
