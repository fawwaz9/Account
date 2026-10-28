import { del, get, patch, post } from "../../services/apiClient";

/** One person on a task you own; mirrors app/Tasks/schemas/sharing.py. */
export interface TaskMember {
  /** The membership's own id, used to remove them. */
  id: string;
  name: string;
  joined_at: string;
}

/** The owner's view of who is on a task; the same shape as `Sharing`. */
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

/** Outcome of accepting a task invite link. */
export type TaskAcceptStatus = "accepted" | "invalid" | "own" | "already" | "full";

// --- the owner ---------------------------------------------------------------

/** Load who is on one of your tasks and whether a link is open. */
export function fetchTaskSharing(userId: string, taskId: string) {
  return get<TaskSharing>(`tasks/${userId}/tasks/${taskId}/sharing`);
}

/** Open a new invite link for your task; an open one stops working, and the token shows once. */
export function makeTaskLink(userId: string, taskId: string) {
  return post<{ token: string; expires_at: string }>(`tasks/${userId}/tasks/${taskId}/sharing/link`, {});
}

/** Cancel your task's open invite link. */
export function cancelTaskLink(userId: string, taskId: string) {
  return del<{ cancelled: boolean }>(`tasks/${userId}/tasks/${taskId}/sharing/link`);
}

/** Take someone off your task; `memberId` is the membership's own id. */
export function removeTaskMember(userId: string, taskId: string, memberId: string) {
  return del<{ removed: boolean }>(`tasks/${userId}/tasks/${taskId}/sharing/members/${memberId}`);
}

// --- the member --------------------------------------------------------------

/** Tasks others share with you. */
export function fetchSharedTasks(userId: string) {
  return get<SharedTask[]>(`tasks/${userId}/shared-tasks`);
}

/** Tick or untick a task shared with you, or change its title or notes. */
export function updateSharedTask(
  userId: string, taskId: string, change: { done?: boolean; title?: string; notes?: string | null },
) {
  return patch<SharedTask>(`tasks/${userId}/shared-tasks/${taskId}`, change);
}

/** Take yourself off someone else's task; their task is untouched. */
export function leaveSharedTask(userId: string, taskId: string) {
  return del<{ left: boolean }>(`tasks/${userId}/shared-tasks/${taskId}`);
}

/** Look up whose task an invite token joins; a POST keeps the token out of URLs and logs. */
export function previewTaskInvite(userId: string, token: string) {
  return post<{ owner_name: string; title: string }>(`tasks/${userId}/shared-tasks/invites/preview`, { token });
}

/** Join a task through an invite token. */
export function acceptTaskInvite(userId: string, token: string) {
  return post<{ status: TaskAcceptStatus }>(`tasks/${userId}/shared-tasks/invites/accept`, { token });
}

/** Fragment prefix telling the invite page a link is for a task. */
export const TASK_LINK_PREFIX = "task:";

/** The invite URL to send; the token rides in the fragment, which never reaches a server. */
export function taskInviteLink(token: string, origin = window.location.origin) {
  return `${origin}/invite#${TASK_LINK_PREFIX}${token}`;
}
