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
