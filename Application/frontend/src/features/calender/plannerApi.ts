import { get, post } from "../../services/apiClient";

/** A stretch of free time given to one task (Phase 4 item 2). */
export interface PlannedBlock {
  task_id: string;
  title: string;
  course_code: string | null;
  due_date: string;
  on_date: string;
  starts_at: string;
  ends_at: string;
  minutes: number;
  reason: string;
}

/** A task that didn't fit before it's due. */
export interface Unplaced {
  task_id: string;
  title: string;
  due_date: string;
  minutes_needed: number;
  minutes_short: number;
  reason: string;
}

/** A proposed week; nothing is stored until accepted. */
export interface WeekPlan {
  starts_on: string;
  ends_on: string;
  blocks: PlannedBlock[];
  unplaced: Unplaced[];
  assumptions: string[];
}

/** A fresh proposal every time: free time changes as the calendar does. */
export const fetchWeekPlan = (userId: string) => get<WeekPlan>(`calendar/${userId}/planner`, { fresh: true });

/** Put the chosen blocks on the calendar, each re-checked on the server. */
export const acceptWeekPlan = (userId: string, blocks: Pick<PlannedBlock, "task_id" | "on_date" | "starts_at" | "ends_at">[]) =>
  post<{ created: number }>(`calendar/${userId}/planner/accept`, {
    blocks: blocks.map(({ task_id, on_date, starts_at, ends_at }) => ({ task_id, on_date, starts_at, ends_at })),
  });
