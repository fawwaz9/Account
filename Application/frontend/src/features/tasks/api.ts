import { del, get, patch, post } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";
import {
  CompletionTiming,
  QuickCapturePreview,
  QuickCaptureResult,
  RecurringTask,
  RecurringTaskCreate,
  RecurringTaskRun,
  RecurringTaskUpdate,
  Reminder,
  ReminderCreate,
  SnoozeRequest,
  Task,
  TaskCreate,
  TaskSnooze,
  TaskUpdate,
} from "./types";

interface TaskQuery {
  /** Checked-off tasks are archived, so both flags are needed to see history. */
  includeDone?: boolean;
  includeArchived?: boolean;
  /** Bounds the due date inclusively, and so excludes undated tasks. */
  start?: string;
  end?: string;
  courseId?: string;
}

export async function fetchTasks(userId: string, options: TaskQuery = {}) {
  const query = [
    options.includeDone ? "include_done=true" : null,
    options.includeArchived ? "include_archived=true" : null,
    options.start ? `start=${options.start}` : null,
    options.end ? `end=${options.end}` : null,
    options.courseId ? `course_id=${options.courseId}` : null,
  ].filter(Boolean);

  const base = endpoints.tasks.list(userId);
  return get<Task[]>(query.length ? `${base}?${query.join("&")}` : base);
}

export async function createTask(userId: string, payload: TaskCreate) {
  return post<Task>(endpoints.tasks.list(userId), payload);
}

export async function updateTask(userId: string, taskId: string, payload: TaskUpdate) {
  return patch<Task>(endpoints.tasks.detail(userId, taskId), payload);
}

/** Checking a task off archives it and stamps when it was finished. */
export async function setTaskDone(userId: string, taskId: string, done: boolean) {
  return updateTask(userId, taskId, { done });
}

export async function deleteTask(userId: string, taskId: string) {
  return del<Task>(endpoints.tasks.detail(userId, taskId));
}

/**
 * Push a task out of the way until a date, and say why.
 *
 * The due date does not move, which is what keeps the timing figures measuring
 * against the date you were given rather than one you picked.
 */
export async function snoozeTask(userId: string, taskId: string, payload: SnoozeRequest) {
  return post<Task>(endpoints.tasks.snooze(userId, taskId), payload);
}

/** Bring a snoozed task back now. The record of having snoozed it stays. */
export async function wakeTask(userId: string, taskId: string) {
  return del<Task>(endpoints.tasks.snooze(userId, taskId));
}

export async function fetchSnoozes(userId: string, taskId: string) {
  return get<TaskSnooze[]>(endpoints.tasks.snoozes(userId, taskId));
}

/** How early or late work has been finished lately. */
export async function fetchTaskTiming(userId: string) {
  return get<CompletionTiming>(endpoints.tasks.timing(userId));
}

/* ===== Reminders ===== */

export async function fetchReminders(userId: string, includeDismissed = false) {
  const base = endpoints.tasks.reminders(userId);
  return get<Reminder[]>(includeDismissed ? `${base}?include_dismissed=true` : base);
}

/**
 * What should be on screen now.
 *
 * This is the whole delivery mechanism: there is no scheduler and no push, so a
 * reminder fires while the app is open and not before. Asking marks them as
 * surfaced, which is why it is not called on every render.
 */
export async function fetchDueReminders(userId: string) {
  return get<Reminder[]>(endpoints.tasks.remindersDue(userId));
}

export async function createReminder(userId: string, payload: ReminderCreate) {
  return post<Reminder>(endpoints.tasks.reminders(userId), payload);
}

/** Acknowledge one. The row stays: what you were reminded of is a record. */
export async function dismissReminder(userId: string, reminderId: string) {
  return post<Reminder>(endpoints.tasks.dismissReminder(userId, reminderId), {});
}

export async function deleteReminder(userId: string, reminderId: string) {
  return del<Reminder>(endpoints.tasks.reminder(userId, reminderId));
}

/* ===== Repeating tasks ===== */

export async function fetchRepeating(userId: string, includeInactive = true) {
  const base = endpoints.tasks.repeating(userId);
  return get<RecurringTask[]>(`${base}?include_inactive=${includeInactive}`);
}

export async function createRepeating(userId: string, payload: RecurringTaskCreate) {
  return post<RecurringTask>(endpoints.tasks.repeating(userId), payload);
}

export async function updateRepeating(
  userId: string,
  ruleId: string,
  payload: RecurringTaskUpdate
) {
  return patch<RecurringTask>(endpoints.tasks.repeatingRule(userId, ruleId), payload);
}

/**
 * Stops the repeat.
 *
 * `dropPending` false keeps the occurrences not yet ticked off. Ones already
 * done always stay — they are a record of work actually done.
 */
export async function deleteRepeating(userId: string, ruleId: string, dropPending = true) {
  return del<RecurringTask>(
    `${endpoints.tasks.repeatingRule(userId, ruleId)}?drop_pending=${dropPending}`
  );
}

/**
 * Write each repeat's occurrences for the rolling window.
 *
 * Idempotent on (rule, due date), so calling it on every task or calendar load
 * is safe, and is what makes a repeating chore simply be there with no
 * scheduler running anywhere.
 */
export async function runRepeating(userId: string) {
  return post<RecurringTaskRun>(endpoints.tasks.repeatingRun(userId), {});
}

/** Cancel one occurrence without ending the repeat. */
export async function skipRepeating(userId: string, ruleId: string, onDate: string) {
  return post<RecurringTask>(
    `${endpoints.tasks.repeatingSkip(userId, ruleId)}?on_date=${onDate}`,
    {}
  );
}

/* ===== Quick capture ===== */

/** What a line would become. A read: it writes nothing. */
export async function previewCapture(userId: string, text: string) {
  const base = endpoints.tasks.quickCapture(userId);
  return get<QuickCapturePreview>(`${base}?text=${encodeURIComponent(text)}`);
}

/** Create the task a line describes, and say how it was read. */
export async function captureTask(userId: string, text: string) {
  return post<QuickCaptureResult>(endpoints.tasks.quickCapture(userId), { text });
}
