import { del, get, patch, post } from "../../services/apiClient";
import { clearApiCache } from "../../services/apiCache";
import { endpoints } from "../../services/endpoints";
import {
  CompletionTiming,
  EstimateRatio,
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
  TimerStop,
} from "./types";

/** Filters for `fetchTasks`. */
interface TaskQuery {
  /** Ticked tasks are archived too, so history needs `includeArchived` as well. */
  includeDone?: boolean;
  includeArchived?: boolean;
  /** Inclusive due-date bound, as is `end`; either one leaves undated tasks out. */
  start?: string;
  end?: string;
  courseId?: string;
}

/** The student's tasks, filtered by done, archived, due range and course. */
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

/** Create a task. */
export async function createTask(userId: string, payload: TaskCreate) {
  return post<Task>(endpoints.tasks.list(userId), payload);
}

/** Patch a task. */
export async function updateTask(userId: string, taskId: string, payload: TaskUpdate) {
  return patch<Task>(endpoints.tasks.detail(userId, taskId), payload);
}

/** Tick or untick a task; ticking archives it and stamps when it was finished. */
export async function setTaskDone(userId: string, taskId: string, done: boolean) {
  return updateTask(userId, taskId, { done });
}

/** Delete a task. */
export async function deleteTask(userId: string, taskId: string) {
  return del<Task>(endpoints.tasks.detail(userId, taskId));
}

/** Hide a task until a date, with a reason; the due date does not move. */
export async function snoozeTask(userId: string, taskId: string, payload: SnoozeRequest) {
  return post<Task>(endpoints.tasks.snooze(userId, taskId), payload);
}

/** Bring a snoozed task back now; its snooze history stays. */
export async function wakeTask(userId: string, taskId: string) {
  return del<Task>(endpoints.tasks.snooze(userId, taskId));
}

/** A task's snooze history. */
export async function fetchSnoozes(userId: string, taskId: string) {
  return get<TaskSnooze[]>(endpoints.tasks.snoozes(userId, taskId));
}

/** How early or late work has been finished lately. */
export async function fetchTaskTiming(userId: string) {
  return get<CompletionTiming>(endpoints.tasks.timing(userId));
}

/** Record how long a task really took; null clears it. */
export async function setActualMinutes(userId: string, taskId: string, minutes: number | null) {
  return updateTask(userId, taskId, { actual_minutes: minutes });
}

/** Start a task's timer; one already running is left as it is. */
export async function startTimer(userId: string, taskId: string) {
  return post<Task>(endpoints.tasks.timerStart(userId, taskId), {});
}

/** Stop a task's timer and add its minutes, unless it ran past twelve hours. */
export async function stopTimer(userId: string, taskId: string) {
  return post<TimerStop>(endpoints.tasks.timerStop(userId, taskId), {});
}

/** How long tasks really take against their estimates. */
export async function fetchEstimateRatio(userId: string) {
  return get<EstimateRatio>(endpoints.tasks.estimates(userId));
}

/* ===== Reminders ===== */

/** The student's reminders, dismissed ones too when asked. */
export async function fetchReminders(userId: string, includeDismissed = false) {
  const base = endpoints.tasks.reminders(userId);
  return get<Reminder[]>(includeDismissed ? `${base}?include_dismissed=true` : base);
}

/** Reminders due now, always from the network, since the read marks them as shown. */
export async function fetchDueReminders(userId: string) {
  // Never the cached answer: this read marks reminders surfaced, so an answer
  // held back for the next poll would be a reminder that never shows.
  return get<Reminder[]>(endpoints.tasks.remindersDue(userId), { fresh: true });
}

/** Create a reminder. */
export async function createReminder(userId: string, payload: ReminderCreate) {
  return post<Reminder>(endpoints.tasks.reminders(userId), payload);
}

/** Acknowledge a reminder; the row is kept as a record. */
export async function dismissReminder(userId: string, reminderId: string) {
  return post<Reminder>(endpoints.tasks.dismissReminder(userId, reminderId), {});
}

/** Delete a reminder. */
export async function deleteReminder(userId: string, reminderId: string) {
  return del<Reminder>(endpoints.tasks.reminder(userId, reminderId));
}

/* ===== Repeating tasks ===== */

/** The student's repeating tasks, paused ones included by default. */
export async function fetchRepeating(userId: string, includeInactive = true) {
  const base = endpoints.tasks.repeating(userId);
  return get<RecurringTask[]>(`${base}?include_inactive=${includeInactive}`);
}

/** Create a repeating task. */
export async function createRepeating(userId: string, payload: RecurringTaskCreate) {
  return post<RecurringTask>(endpoints.tasks.repeating(userId), payload);
}

/** Patch a repeating task. */
export async function updateRepeating(
  userId: string,
  ruleId: string,
  payload: RecurringTaskUpdate
) {
  return patch<RecurringTask>(endpoints.tasks.repeatingRule(userId, ruleId), payload);
}

/** End a repeat; `dropPending` false keeps its open occurrences, and done ones always stay. */
export async function deleteRepeating(userId: string, ruleId: string, dropPending = true) {
  return del<RecurringTask>(
    `${endpoints.tasks.repeatingRule(userId, ruleId)}?drop_pending=${dropPending}`
  );
}

/**
 * Write the due occurrences of every repeating task; the Tasks list runs it on each load.
 * Empties the GET cache only when it wrote something.
 */
export async function runRepeating(userId: string) {
  // Run on every load and usually writes nothing, so it clears the GET cache
  // only when it wrote something (apiCache.ts).
  const run = await post<RecurringTaskRun>(endpoints.tasks.repeatingRun(userId), {}, { keepCache: true });
  if (run.created > 0) clearApiCache();
  return run;
}

/** Cancel one occurrence of a repeat without ending it. */
export async function skipRepeating(userId: string, ruleId: string, onDate: string) {
  return post<RecurringTask>(
    `${endpoints.tasks.repeatingSkip(userId, ruleId)}?on_date=${onDate}`,
    {}
  );
}

/* ===== Quick capture ===== */

/** How a capture line would be read; writes nothing. */
export async function previewCapture(userId: string, text: string) {
  const base = endpoints.tasks.quickCapture(userId);
  return get<QuickCapturePreview>(`${base}?text=${encodeURIComponent(text)}`);
}

/** Create the task a capture line describes, and return how it was read. */
export async function captureTask(userId: string, text: string) {
  return post<QuickCaptureResult>(endpoints.tasks.quickCapture(userId), { text });
}
