import { del, get, patch, post } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";
import { Task, TaskCreate, TaskUpdate } from "./types";

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
