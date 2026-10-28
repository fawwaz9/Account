/** The Fitness page beyond teams (Phase 3 items 6-8 and 13): types and API calls under /api/fitness. */

import { del, get, post, put } from "../../services/apiClient";

/** A partner or teammate who is also looking for someone to train with. */
export interface GymBuddy {
  name: string;
  times: string | null;
  note: string | null;
  /** How you know them: "partner" first, then team names. */
  via: string;
}

/** Your gym-buddy status, and connections looking too (empty while you aren't). */
export interface GymBuddies {
  looking: boolean;
  times: string | null;
  note: string | null;
  buddies: GymBuddy[];
}

/** Your status and the connections looking too. */
export const fetchGymBuddies = (userId: string) => get<GymBuddies>(`fitness/${userId}/gym-buddy`);

/** Say whether you're looking, with when and a note. */
export const saveGymBuddy = (userId: string, looking: boolean, times: string | null, note: string | null) =>
  put<GymBuddies>(`fitness/${userId}/gym-buddy`, { looking, times, note });

/** What an activity can be. */
export type ActivityKind = "walk" | "run" | "cycle" | "swim" | "gym" | "sport" | "yoga" | "hike" | "other";

/** A logged activity and the points it earned under its formula version. */
export interface Activity {
  id: string;
  /** YYYY-MM-DD. */
  on_date: string;
  kind: ActivityKind;
  minutes: number;
  points: number;
  formula_version: number;
  note: string | null;
}

/** This week against the goal, the 8 weeks before, a suggested goal, and the last 28 days. */
export interface Exertion {
  /** This week's Monday. */
  week_start: string;
  this_week: number;
  goal: number | null;
  suggestion: { points: number | null; reason: string };
  weeks: { week_start: string; points: number }[];
  recent: Activity[];
}

/** This week's points, the goal and a suggestion. */
export const fetchExertion = (userId: string) => get<Exertion>(`fitness/${userId}/exertion`);

/** Set the weekly goal, or clear it with null. */
export const setExertionGoal = (userId: string, goal: number | null) =>
  put<Exertion>(`fitness/${userId}/exertion/goal`, { goal });

/** Log an activity; its points are worked out now and never rewritten. */
export const logActivity = (userId: string, activity: { on_date: string; kind: ActivityKind; minutes: number; note: string | null }) =>
  post<Activity>(`fitness/${userId}/activities`, activity);

/** Delete one of your activities. */
export async function deleteActivity(userId: string, activityId: string) {
  return del<{ deleted: boolean }>(`fitness/${userId}/activities/${activityId}`);
}
