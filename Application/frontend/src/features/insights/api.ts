import { get, post } from "../../services/apiClient";

/** Where each term-simulator slider starts (Phase 4 item 9). */
export interface TermDefaults {
  sleep_hours: number;
  class_hours: number;
  study_hours: number;
  work_hours: number;
  workouts_per_week: number;
  workout_minutes: number;
  overhead_hours: number;
  exertion_goal: number | null;
}

/** One simulated week. Study hours null means "not set": nothing academic renders. */
export interface TermIn {
  sleep_hours: number;
  class_hours: number;
  study_hours: number | null;
  work_hours: number | null;
  workouts_per_week: number;
  workout_minutes: number;
  overhead_hours: number;
  monthly_spending_change: number;
}

/** The simulated week across the rooms. */
export interface TermResult {
  time: {
    rooms: { room: "academic" | "money" | "body" | "life"; label: string; hours: number }[];
    total: number;
    fits: boolean;
    short_by: number;
    spare: number;
  };
  money: { baseline_ending: number; scenario_ending: number; difference: number; lowest: number;
    negative_on: string | null; notes: string[] } | null;
  body: { points_per_week: number; goal: number | null; meets_goal: boolean | null };
  /** Only when study hours were set directly (§13.19). */
  academic: { study_hours: number; estimated_hours: number; coverage: number | null; reading: string;
    bands: { code: string; current: number; best: number; worst: number }[] } | null;
  assumptions: string[];
}

export const fetchTermDefaults = (userId: string) => get<TermDefaults>(`insights/${userId}/term/defaults`);

/** Simulate a week; it stores nothing, so it keeps the GET cache. */
export const simulateTerm = (userId: string, body: TermIn) =>
  post<TermResult>(`insights/${userId}/term`, body, { keepCache: true });
