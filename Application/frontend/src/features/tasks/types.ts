/** Task, reminder, timing and repeating-task types; they mirror app/Tasks/schemas. */
// One repeat rule serves class times, payments and chores, so it lives in the calendar feature.
import { Recurrence } from "../calender/types";

/** A task as the API returns it, with server-computed risk and sharing. */
export interface Task {
  id: string;
  title: string;
  notes: string | null;
  /** YYYY-MM-DD, or null for no deadline; a dated task also shows on the calendar. */
  due_date: string | null;
  due_time: string | null;
  /** The student's estimate in minutes, so a week's load reads as hours. */
  estimated_minutes: number | null;
  course_id: string | null;
  /** Denormalised by the API; coursework is grouped by this, not by a tag. */
  course_code: string | null;
  tags: string[];
  /** 1 (lowest) to 5 (highest); coursework is seeded from its grade category. */
  priority: number;
  done: boolean;
  /** When it was ticked off, naive UTC; null while open. */
  completed_at: string | null;
  archived: boolean;
  created_at: string | null;
  /** Set when a dated grade raised it; it closes itself when the score lands, never reopening. */
  grade_id: string | null;
  /** Set when a repeating task wrote this occurrence; the editor warns an edit is for this day. */
  recurring_id: string | null;
  /** How far behind target its course is, from the API; null when there is nothing to flag. */
  risk: RiskBand | null;
  /** Hidden from the list until this date; the due date is unchanged. */
  snoozed_until: string | null;
  snooze_count: number;
  /** Why it was last pushed back, shown on its row. */
  last_snooze_reason: string | null;
  /** Minutes it really took: the answer given on completion, or the timer's total. */
  actual_minutes?: number | null;
  /** When the running timer started, UTC, kept by the server; null when none runs. */
  timer_started_at?: string | null;
  /** Names of the people it is shared with; empty when it is yours alone. */
  shared_with?: string[];
}

/** Result of stopping a task's timer. */
export interface TimerStop {
  task: Task;
  /** Minutes the stop added; 0 when it recorded nothing. */
  added_minutes: number;
  /** True when the timer ran past twelve hours, so nothing was recorded. */
  discarded: boolean;
}

/** How long tasks really take against their estimates. */
export interface EstimateRatio {
  /** Total actual over total estimated; null until `needed` tasks have both. */
  ratio: number | null;
  /** Finished tasks in the window with both an estimate and an actual. */
  tasks: number;
  /** How many such tasks a ratio requires. */
  needed: number;
  estimated_minutes: number;
  actual_minutes: number;
  /** Whether the workload forecast is using it. */
  applied: boolean;
}

/** Request body for snoozing a task until a date, with an optional reason. */
export interface SnoozeRequest {
  until: string;
  reason: string | null;
}

/** A standalone reminder at a local wall-clock time. */
export interface Reminder {
  id: string;
  title: string;
  notes: string | null;
  /** Naive local wall time with no offset, unlike every other timestamp, which is UTC. */
  remind_at: string;
  course_id: string | null;
  course_code: string | null;
  /** When the app first showed it, naive UTC; null until then. */
  fired_at: string | null;
  /** When it was pushed to a device; the app then doesn't announce it again. */
  pushed_at?: string | null;
  dismissed_at: string | null;
  created_at: string | null;
  /** Its time has passed and nobody has dismissed it; from the API. */
  due: boolean;
}

/** Request body for a reminder. */
export interface ReminderCreate {
  title: string;
  notes: string | null;
  remind_at: string;
  course_id: string | null;
}

/** Patch body for a reminder. */
export type ReminderUpdate = Partial<ReminderCreate>;

/** One past snooze of a task. */
export interface TaskSnooze {
  id: string;
  /** When it was snoozed, naive UTC. */
  snoozed_at: string;
  until: string;
  reason: string | null;
}

/** How far below target a course is: mild 0-5, moderate 5-10, severe over 10 points. */
export type RiskBand = "mild" | "moderate" | "severe";

/** How early or late the tasks finished in one window were. */
export interface TimingWindow {
  label: string;
  starts_on: string;
  ends_on: string;
  /** Completed tasks that had a due date; undated work is left out. */
  counted: number;
  /** Mean signed days from the due date, positive late and negative early; null if none. */
  mean_days: number | null;
  /** Percentage finished on or before the due date; null when nothing was counted. */
  on_time_percent: number | null;
  early_count: number;
  /** Days early, positive, across the early ones only. */
  early_mean_days: number | null;
  late_count: number;
  /** Days late, positive, across the late ones only. */
  late_mean_days: number | null;
}

/** Completion timing for the past week and this month. */
export interface CompletionTiming {
  past_week: TimingWindow;
  this_month: TimingWindow;
  /** Completed tasks with no due date, counted by no figure above. */
  undated_completed: number;
}

/** Request body for creating a task. */
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

/** Lowest priority; the three bounds mirror the backend's Grades/utils/enums.py. */
export const MIN_PRIORITY = 1;
/** Priority a new task starts with. */
export const DEFAULT_PRIORITY = 3;
/** Highest priority. */
export const MAX_PRIORITY = 5;

/** Word for each priority step, shown beside the number. */
export const PRIORITY_LABELS: Record<number, string> = {
  1: "Lowest",
  2: "Low",
  3: "Normal",
  4: "High",
  5: "Highest",
};

/** Patch body for a task: any create field, plus done, archived and actual minutes. */
export type TaskUpdate = Partial<TaskCreate> & {
  done?: boolean;
  archived?: boolean;
  /** Null clears it. */
  actual_minutes?: number | null;
};

/* ===== Repeating tasks ===== */

/**
 * A repeating task: a rule plus a template whose occurrences are real task rows,
 * ticked off one by one and written a little way ahead.
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
  /** False pauses the series, so no new occurrences are written. */
  active: boolean;
  skipped_dates: string[];
  created_at: string | null;
  /** The next occurrence still outstanding, or null once the rule has run out. */
  next_due_on: string | null;
}

/** Request body for a repeating task. */
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

/** Patch body for a repeating task. */
export type RecurringTaskUpdate = Partial<RecurringTaskCreate>;

/** What writing a repeating task's occurrences created. */
export interface RecurringTaskRun {
  created: number;
  tasks: Task[];
}

/* ===== Quick capture ===== */

/** How one typed capture line was parsed, shown as the student types and before any save. */
export interface QuickCapturePreview {
  text: string;
  title: string;
  due_date: string | null;
  estimated_minutes: number | null;
  course_id: string | null;
  course_code: string | null;
  /** A typed code matching none or several of your courses; it stays in the title. */
  unmatched_course: string | null;
  /** Which kinds parsed: course, date, duration, amount, score. */
  matched: string[];
  /** False when there is nothing left to make a task from. */
  can_create: boolean;
}

/** The task a capture line created, and how the line was parsed. */
export interface QuickCaptureResult {
  task: Task;
  preview: QuickCapturePreview;
}
