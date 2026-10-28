/** Teams on the Fitness page: types mirroring app/Teams/schemas/team.py, and the API calls. */

import { del, get, patch, post, put } from "../../services/apiClient";

/** A team's results from confirmed games only. */
export interface TeamRecord {
  wins: number;
  losses: number;
  ties: number;
  points_for: number;
  points_against: number;
  /** Games recorded but not yet confirmed, or disputed; left out of the figures. */
  unconfirmed: number;
}

/** A team as listed: name, captain, members and record. */
export interface TeamSummary {
  team_id: string;
  name: string;
  sport: string | null;
  captain_name: string;
  is_captain: boolean;
  member_names: string[];
  record: TeamRecord;
}

/** One recorded game and where its confirmation stands. */
export interface Game {
  game_id: string;
  played_on: string;
  opponent: string;
  our_score: number;
  their_score: number;
  recorded_by_name: string;
  /** You recorded it, so someone else must confirm it. */
  recorded_by_me: boolean;
  confirmed_by_name: string | null;
  /** When confirmed, naive UTC; null while waiting. */
  confirmed_at: string | null;
  disputed_by_name: string | null;
  disputed_by_me: boolean;
  /** Our score as the disputer saw it; null when undisputed. */
  disputed_our: number | null;
  disputed_their: number | null;
}

/** A team with its games; members and link only for the captain. */
export interface TeamDetail extends TeamSummary {
  games: Game[];
  /** Captain's view only; null for anyone else. */
  members: { id: string; name: string; joined_at: string }[] | null;
  /** The open invite link, captain's view only. */
  link: { expires_at: string } | null;
  /** How it's listed on campus, captain's view only (Phase 3 items 8-9). */
  listing?: TeamListing | null;
}

/** How a team is listed on campus: the directory and the campus board. */
export interface TeamListing {
  listed: boolean;
  level: "casual" | "intermediate" | "competitive" | null;
  area: string | null;
  looking_for_players: boolean;
  blurb: string | null;
}

/** Body to record or correct a game. */
export interface GameInput {
  played_on: string;
  opponent: string;
  our_score: number;
  their_score: number;
}

/** Outcome of opening a team invite link. */
export type TeamAcceptStatus = "accepted" | "invalid" | "own" | "already" | "full";

/** Fetch your teams. */
export const fetchTeams = (userId: string) => get<TeamSummary[]>(`teams/${userId}`);
/** Fetch one team with its games. */
export const fetchTeam = (userId: string, teamId: string) => get<TeamDetail>(`teams/${userId}/${teamId}`);
/** Create a team with you as captain. */
export const createTeam = (userId: string, name: string, sport: string | null) =>
  post<TeamDetail>(`teams/${userId}`, { name, sport });
/** Rename a team; captain only. */
export const renameTeam = (userId: string, teamId: string, name: string) =>
  patch<TeamDetail>(`teams/${userId}/${teamId}`, { name });
/** Change how a team is listed on campus; captain only. */
export const updateTeamListing = (userId: string, teamId: string, listing: Partial<TeamListing>) =>
  patch<TeamDetail>(`teams/${userId}/${teamId}`, listing);
/** Delete a team with its games, members and link. */
export const removeTeam = (userId: string, teamId: string) => del<{ deleted: boolean }>(`teams/${userId}/${teamId}`);
/** Create the team's invite link. */
export const makeTeamLink = (userId: string, teamId: string) =>
  post<{ token: string; expires_at: string }>(`teams/${userId}/${teamId}/link`, {});
/** Cancel the team's invite link. */
export const cancelTeamLink = (userId: string, teamId: string) =>
  del<{ cancelled: boolean }>(`teams/${userId}/${teamId}/link`);
/** Take a member off the team; captain only. */
export const removeTeamMember = (userId: string, teamId: string, memberId: string) =>
  del<{ removed: boolean }>(`teams/${userId}/${teamId}/members/${memberId}`);
/** Leave a team you are on. */
export const leaveTeam = (userId: string, teamId: string) => del<{ left: boolean }>(`teams/${userId}/${teamId}/membership`);

/** Record a game; it counts once someone else confirms it. */
export const recordGame = (userId: string, teamId: string, game: GameInput) =>
  post<TeamDetail>(`teams/${userId}/${teamId}/games`, game);
/** Correct a game you recorded, before it is confirmed. */
export const correctGame = (userId: string, teamId: string, gameId: string, game: GameInput) =>
  put<{ ok: boolean }>(`teams/${userId}/${teamId}/games/${gameId}`, game);
/** Confirm a game someone else recorded. */
export const confirmGame = (userId: string, teamId: string, gameId: string) =>
  post<{ ok: boolean }>(`teams/${userId}/${teamId}/games/${gameId}/confirm`, {});
/** Dispute a game with the score as you saw it. */
export const disputeGame = (userId: string, teamId: string, gameId: string, our_score: number, their_score: number) =>
  post<{ ok: boolean }>(`teams/${userId}/${teamId}/games/${gameId}/dispute`, { our_score, their_score });
/** Delete a game. */
export const removeGame = (userId: string, teamId: string, gameId: string) =>
  del<{ ok: boolean }>(`teams/${userId}/${teamId}/games/${gameId}`);

/** Who invited you to which team; a POST, so the token stays out of URLs. */
export const previewTeamInvite = (userId: string, token: string) =>
  post<{ captain_name: string; team_name: string; sport: string | null }>(`teams/${userId}/invites/preview`, { token });
/** Join a team by its invite token. */
export const acceptTeamInvite = (userId: string, token: string) =>
  post<{ status: TeamAcceptStatus }>(`teams/${userId}/invites/accept`, { token });

/** Fragment prefix marking a team invite link. */
export const TEAM_LINK_PREFIX = "team:";
/** The team link to send; the token rides in the fragment. */
export function teamInviteLink(token: string, origin = window.location.origin) {
  return `${origin}/invite#${TEAM_LINK_PREFIX}${token}`;
}

/** A record as wins–losses–ties, e.g. "3–1–0". */
export function recordLine(record: TeamRecord) {
  return `${record.wins}–${record.losses}–${record.ties}`;
}
