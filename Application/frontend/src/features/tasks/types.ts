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
  /** 1 to 5, 5 most important. Coursework is seeded from its grade category. */
  priority: number;
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
  /** Hidden from the list until this date. The due date is unaffected. */
  snoozed_until: string | null;
  /** How many times it has been pushed back. */
  snooze_count: number;
  /** Why it was last pushed back, so a blocked task says so on its own row. */
  last_snooze_reason: string | null;
}

export interface SnoozeRequest {
  until: string;
  reason: string | null;
}

/** Mirrors app/Tasks/schemas/reminder.py. */
export interface Reminder {
  id: string;
  title: string;
  notes: string | null;
  /**
   * Local wall time, sent and received without an offset. "Remind me at 09:00"
   * means nine o'clock where you are, and should still mean that after the
   * clocks change — which is why this is not UTC like every other timestamp.
   */
  remind_at: string;
  course_id: string | null;
  course_code: string | null;
  fired_at: string | null;
  dismissed_at: string | null;
  created_at: string | null;
  /** Its moment has passed and nobody has dismissed it. Computed by the API. */
  due: boolean;
}

export interface ReminderCreate {
  title: string;
  notes: string | null;
  remind_at: string;
  course_id: string | null;
}

export type ReminderUpdate = Partial<ReminderCreate>;

export interface TaskSnooze {
  id: string;
  snoozed_at: string;
  until: string;
  reason: string | null;
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
  priority: number;
}

/** The lowest, default and highest a priority may be. Mirrors Grades/utils/enums.py. */
export const MIN_PRIORITY = 1;
export const DEFAULT_PRIORITY = 3;
export const MAX_PRIORITY = 5;

/** What each step means, so the number is not the only thing on offer. */
export const PRIORITY_LABELS: Record<number, string> = {
  1: "Lowest",
  2: "Low",
  3: "Normal",
  4: "High",
  5: "Highest",
};

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
  /** Stamped onto every occurrence this rule writes. */
  priority: number;
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
  priority: number;
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
