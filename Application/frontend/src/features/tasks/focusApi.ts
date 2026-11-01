import { get, post } from "../../services/apiClient";

/** One focus session (Phase 4 item 4). */
export interface FocusSession {
  id: string;
  course_id: string | null;
  course_code: string | null;
  started_at: string;
  ended_at: string | null;
  minutes: number | null;
}

/** Focus on one course, with its grade now. */
export interface CourseFocus {
  course_id: string | null;
  course_code: string;
  minutes_this_week: number;
  minutes_term: number;
  grade: number | null;
}

/** The running session, and focus per course. */
export interface FocusSummary {
  running: FocusSession | null;
  courses: CourseFocus[];
  total_this_week: number;
}

export const fetchFocus = (userId: string) => get<FocusSummary>(`tasks/${userId}/focus`, { fresh: true });
export const startFocus = (userId: string, courseId: string | null) =>
  post<FocusSession>(`tasks/${userId}/focus/start`, { course_id: courseId });
export const stopFocus = (userId: string) => post<FocusSession | null>(`tasks/${userId}/focus/stop`, {});
