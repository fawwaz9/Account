import { del, get, patch, post, put } from "../../services/apiClient";

/** Mirrors app/Teams/schemas/team.py (Phase 2 item 11, D26). */
export interface TeamRecord {
  wins: number;
  losses: number;
  ties: number;
  points_for: number;
  points_against: number;
  unconfirmed: number;
}

export interface TeamSummary {
  team_id: string;
  name: string;
  sport: string | null;
  captain_name: string;
  is_captain: boolean;
  member_names: string[];
  record: TeamRecord;
}

export interface Game {
  game_id: string;
  played_on: string;
  opponent: string;
  our_score: number;
  their_score: number;
  recorded_by_name: string;
  recorded_by_me: boolean;
  confirmed_by_name: string | null;
  confirmed_at: string | null;
  disputed_by_name: string | null;
  disputed_by_me: boolean;
  disputed_our: number | null;
  disputed_their: number | null;
}

export interface TeamDetail extends TeamSummary {
  games: Game[];
  /** The captain's view only. */
  members: { id: string; name: string; joined_at: string }[] | null;
  link: { expires_at: string } | null;
}

export interface GameInput {
  played_on: string;
  opponent: string;
  our_score: number;
  their_score: number;
}

export type TeamAcceptStatus = "accepted" | "invalid" | "own" | "already" | "full";

export const fetchTeams = (userId: string) => get<TeamSummary[]>(`teams/${userId}`);
export const fetchTeam = (userId: string, teamId: string) => get<TeamDetail>(`teams/${userId}/${teamId}`);
export const createTeam = (userId: string, name: string, sport: string | null) =>
  post<TeamDetail>(`teams/${userId}`, { name, sport });
export const renameTeam = (userId: string, teamId: string, name: string) =>
  patch<TeamDetail>(`teams/${userId}/${teamId}`, { name });
/** The team and its games, members and link all go. */
export const removeTeam = (userId: string, teamId: string) => del<{ deleted: boolean }>(`teams/${userId}/${teamId}`);
export const makeTeamLink = (userId: string, teamId: string) =>
  post<{ token: string; expires_at: string }>(`teams/${userId}/${teamId}/link`, {});
export const cancelTeamLink = (userId: string, teamId: string) =>
  del<{ cancelled: boolean }>(`teams/${userId}/${teamId}/link`);
export const removeTeamMember = (userId: string, teamId: string, memberId: string) =>
  del<{ removed: boolean }>(`teams/${userId}/${teamId}/members/${memberId}`);
export const leaveTeam = (userId: string, teamId: string) => del<{ left: boolean }>(`teams/${userId}/${teamId}/membership`);

export const recordGame = (userId: string, teamId: string, game: GameInput) =>
  post<TeamDetail>(`teams/${userId}/${teamId}/games`, game);
export const correctGame = (userId: string, teamId: string, gameId: string, game: GameInput) =>
  put<{ ok: boolean }>(`teams/${userId}/${teamId}/games/${gameId}`, game);
export const confirmGame = (userId: string, teamId: string, gameId: string) =>
  post<{ ok: boolean }>(`teams/${userId}/${teamId}/games/${gameId}/confirm`, {});
export const disputeGame = (userId: string, teamId: string, gameId: string, our_score: number, their_score: number) =>
  post<{ ok: boolean }>(`teams/${userId}/${teamId}/games/${gameId}/dispute`, { our_score, their_score });
export const removeGame = (userId: string, teamId: string, gameId: string) =>
  del<{ ok: boolean }>(`teams/${userId}/${teamId}/games/${gameId}`);

export const previewTeamInvite = (userId: string, token: string) =>
  post<{ captain_name: string; team_name: string; sport: string | null }>(`teams/${userId}/invites/preview`, { token });
export const acceptTeamInvite = (userId: string, token: string) =>
  post<{ status: TeamAcceptStatus }>(`teams/${userId}/invites/accept`, { token });

export const TEAM_LINK_PREFIX = "team:";
export function teamInviteLink(token: string, origin = window.location.origin) {
  return `${origin}/invite#${TEAM_LINK_PREFIX}${token}`;
}

/** "3–1–0": wins, losses, ties. */
export function recordLine(record: TeamRecord) {
  return `${record.wins}–${record.losses}–${record.ties}`;
}
