import { del, get, patch, post } from "../../services/apiClient";

/** Mirrors app/Tasks/schemas/sharing.py (Phase 2 item 9a, D23). */
export interface TaskMember {
  id: string;
  name: string;
  joined_at: string;
}

export interface TaskSharing {
  members: TaskMember[];
  link: { expires_at: string } | null;
  /** False for one of a repeat, which can't be shared. */
  shareable: boolean;
  max_members: number;
}

/** Someone else's task you are on: only the fields a member may see. */
export interface SharedTask {
  task_id: string;
  owner_name: string;
  title: string;
  notes: string | null;
  due_date: string | null;
  due_time: string | null;
  done: boolean;
  completed_at: string | null;
  /** Everyone on it besides the owner, you included. */
  member_names: string[];
}

export type TaskAcceptStatus = "accepted" | "invalid" | "own" | "already" | "full";

// --- the owner ---------------------------------------------------------------

export function fetchTaskSharing(userId: string, taskId: string) {
  return get<TaskSharing>(`tasks/${userId}/tasks/${taskId}/sharing`);
}

/** A fresh link; any open one stops working. The token is shown this once. */
export function makeTaskLink(userId: string, taskId: string) {
  return post<{ token: string; expires_at: string }>(`tasks/${userId}/tasks/${taskId}/sharing/link`, {});
}

export function cancelTaskLink(userId: string, taskId: string) {
  return del<{ cancelled: boolean }>(`tasks/${userId}/tasks/${taskId}/sharing/link`);
}

/** Take someone off your task. `memberId` is the membership's own id. */
export function removeTaskMember(userId: string, taskId: string, memberId: string) {
  return del<{ removed: boolean }>(`tasks/${userId}/tasks/${taskId}/sharing/members/${memberId}`);
}

// --- the member --------------------------------------------------------------

export function fetchSharedTasks(userId: string) {
  return get<SharedTask[]>(`tasks/${userId}/shared-tasks`);
}

export function updateSharedTask(
  userId: string, taskId: string, change: { done?: boolean; title?: string; notes?: string | null },
) {
  return patch<SharedTask>(`tasks/${userId}/shared-tasks/${taskId}`, change);
}

/** Take yourself off someone else's task. Their task is untouched. */
export function leaveSharedTask(userId: string, taskId: string) {
  return del<{ left: boolean }>(`tasks/${userId}/shared-tasks/${taskId}`);
}

/** Whose task a link joins. POST, so the token stays out of URLs and logs. */
export function previewTaskInvite(userId: string, token: string) {
  return post<{ owner_name: string; title: string }>(`tasks/${userId}/shared-tasks/invites/preview`, { token });
}

export function acceptTaskInvite(userId: string, token: string) {
  return post<{ status: TaskAcceptStatus }>(`tasks/${userId}/shared-tasks/invites/accept`, { token });
}

/** The prefix that tells the invite page a link is for a task, not a partner. */
export const TASK_LINK_PREFIX = "task:";

/** The link to send: the token rides in the fragment, which browsers never send to a server. */
export function taskInviteLink(token: string, origin = window.location.origin) {
  return `${origin}/invite#${TASK_LINK_PREFIX}${token}`;
}
