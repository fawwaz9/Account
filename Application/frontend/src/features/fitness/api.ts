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

/** One opted-in player on a team's board this week. */
export interface BoardRow {
  name: string;
  points: number;
  is_me: boolean;
}

/** A team's board: empty for you until you opt in. */
export interface TeamBoard {
  opted_in: boolean;
  week_start: string;
  rows: BoardRow[];
}

/** This week's campus board: listed teams, never people; empty below the floor. */
export interface CampusBoard {
  floor: number;
  week_start: string | null;
  teams: { team_name: string; sport: string | null; points: number }[];
}

/** A listed team in the directory: never a member's name. */
export interface DirectoryTeam {
  team_id: string;
  name: string;
  sport: string | null;
  level: string | null;
  area: string | null;
  looking: boolean;
  blurb: string | null;
  members: number;
  last_game_on: string | null;
  /** No game in 30 days: shown greyed. */
  dormant: boolean;
  /** You're on it. */
  mine: boolean;
  /** Your request to join it, if any. */
  requested: "pending" | "accepted" | "declined" | null;
}

/** The directory: empty until `floor` teams are listed. */
export interface Directory {
  floor: number;
  teams: DirectoryTeam[];
}

/** One of your own requests to join a team. */
export interface MyJoinRequest {
  id: string;
  team_name: string;
  message: string | null;
  status: "pending" | "accepted" | "declined";
  created_at: string;
}

/** A waiting request to join your team, as its captain sees it. */
export interface TeamJoinRequest {
  request_id: string;
  requester_name: string;
  message: string | null;
  created_at: string;
}

/** A team's board this week. */
export const fetchTeamBoard = (userId: string, teamId: string) =>
  get<TeamBoard>(`fitness/${userId}/teams/${teamId}/board`);

/** This week's campus board. */
export const fetchCampusBoard = (userId: string) => get<CampusBoard>(`fitness/${userId}/campus-board`);

/** The league directory. */
export const fetchDirectory = (userId: string) => get<Directory>(`fitness/${userId}/directory`);

/** Ask to join a listed team; answers "sent" or why not. */
export const joinTeam = (userId: string, teamId: string, message: string | null) =>
  post<{ status: string }>(`fitness/${userId}/directory/${teamId}/join`, { message });

/** Your own requests to join teams. */
export const fetchMyJoinRequests = (userId: string) => get<MyJoinRequest[]>(`fitness/${userId}/join-requests`);

/** Take back a waiting request; you can ask again, so nothing to confirm. */
export const withdrawJoinRequest = (userId: string, requestId: string) =>
  del<{ deleted: boolean }>(`fitness/${userId}/join-requests/${requestId}`);

/** The waiting requests to join a team you captain. */
export const fetchTeamJoinRequests = (userId: string, teamId: string) =>
  get<TeamJoinRequest[]>(`fitness/${userId}/teams/${teamId}/join-requests`);

/** Accept or decline a request to join your team. */
export const answerJoinRequest = (userId: string, requestId: string, accept: boolean) =>
  post<{ status: string }>(`fitness/${userId}/join-requests/${requestId}/answer`, { accept });
