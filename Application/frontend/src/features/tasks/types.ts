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
