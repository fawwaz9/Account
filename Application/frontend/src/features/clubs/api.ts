/** Clubs (Phase 3 item 10): types mirroring app/Clubs/schemas/club.py, and the API calls. */

import { del, get, patch, post } from "../../services/apiClient";

/** A club as listed. */
export interface ClubSummary {
  club_id: string;
  name: string;
  about: string | null;
  owner_name: string;
  is_owner: boolean;
  /** Everyone in it, the owner included. */
  member_count: number;
}

/** An announcement. */
export interface ClubPost {
  post_id: string;
  body: string;
  created_at: string;
}

/** A poll as someone in the club sees it: counts, never who voted for what. */
export interface ClubPoll {
  poll_id: string;
  question: string;
  options: string[];
  closes_on: string | null;
  counts: number[];
  my_vote: number | null;
  open: boolean;
}

/** A club event. */
export interface ClubEvent {
  event_id: string;
  title: string;
  on_date: string;
  start_time: string | null;
  end_time: string | null;
  location: string | null;
}

/** A club event for the calendar, with its club. */
export interface CalendarClubEvent extends ClubEvent {
  club_id: string;
  club_name: string;
}

/** A club with its posts, polls and upcoming events; members and link for its owner. */
export interface ClubDetail extends ClubSummary {
  posts: ClubPost[];
  polls: ClubPoll[];
  events: ClubEvent[];
  members: { id: string; name: string; joined_at: string }[] | null;
  link: { expires_at: string } | null;
}

/** Outcome of opening a club link. */
export type ClubAcceptStatus = "accepted" | "invalid" | "own" | "already" | "full";

/** The clubs you own, then those you're in. */
export const fetchClubs = (userId: string) => get<ClubSummary[]>(`clubs/${userId}`);
/** One club. */
export const fetchClub = (userId: string, clubId: string) => get<ClubDetail>(`clubs/${userId}/${clubId}`);
/** Make a club with you as its owner. */
export const createClub = (userId: string, name: string, about: string | null) =>
  post<ClubDetail>(`clubs/${userId}`, { name, about });
/** Rename a club or change its line; owner only. */
export const updateClub = (userId: string, clubId: string, fields: { name?: string; about?: string | null }) =>
  patch<ClubDetail>(`clubs/${userId}/${clubId}`, fields);
/** Delete a club and everything in it. */
export async function deleteClub(userId: string, clubId: string) {
  return del<{ deleted: boolean }>(`clubs/${userId}/${clubId}`);
}
/** Make the club's join link. */
export const makeClubLink = (userId: string, clubId: string) =>
  post<{ token: string; expires_at: string }>(`clubs/${userId}/${clubId}/link`, {});
/** Cancel the club's join link. */
export const cancelClubLink = (userId: string, clubId: string) =>
  del<{ cancelled: boolean }>(`clubs/${userId}/${clubId}/link`);
/** Take someone out of the club. */
export async function deleteClubMember(userId: string, clubId: string, memberId: string) {
  return del<{ removed: boolean }>(`clubs/${userId}/${clubId}/members/${memberId}`);
}
/** Leave a club you're in. */
export const leaveClub = (userId: string, clubId: string) => del<{ left: boolean }>(`clubs/${userId}/${clubId}/membership`);
/** Post an announcement; owner only. */
export const addClubPost = (userId: string, clubId: string, body: string) =>
  post<ClubDetail>(`clubs/${userId}/${clubId}/posts`, { body });
/** Delete an announcement. */
export async function deleteClubPost(userId: string, clubId: string, postId: string) {
  return del<{ deleted: boolean }>(`clubs/${userId}/${clubId}/posts/${postId}`);
}
/** Ask the club a question; owner only. */
export const addClubPoll = (userId: string, clubId: string, question: string, options: string[], closesOn: string | null) =>
  post<ClubDetail>(`clubs/${userId}/${clubId}/polls`, { question, options, closes_on: closesOn });
/** Delete a poll and its votes. */
export async function deleteClubPoll(userId: string, clubId: string, pollId: string) {
  return del<{ deleted: boolean }>(`clubs/${userId}/${clubId}/polls/${pollId}`);
}
/** Vote in a poll, or change your vote. */
export const voteClubPoll = (userId: string, clubId: string, pollId: string, option: number) =>
  post<ClubDetail>(`clubs/${userId}/${clubId}/polls/${pollId}/vote`, { option });
/** Add a club event, which appears on every member's calendar; owner only. */
export const addClubEvent = (userId: string, clubId: string, event: Omit<ClubEvent, "event_id">) =>
  post<ClubDetail>(`clubs/${userId}/${clubId}/events`, event);
/** Delete a club event. */
export async function deleteClubEvent(userId: string, clubId: string, eventId: string) {
  return del<{ deleted: boolean }>(`clubs/${userId}/${clubId}/events/${eventId}`);
}
/** Club events for your calendar in a window. */
export const fetchClubEvents = (userId: string, start: string, end: string) =>
  get<CalendarClubEvent[]>(`clubs/${userId}/events?start=${start}&end=${end}`);
/** Whose club a link joins. */
export const previewClubInvite = (userId: string, token: string) =>
  post<{ owner_name: string; club_name: string }>(`clubs/${userId}/invites/preview`, { token });
/** Join a club through its link. */
export const acceptClubInvite = (userId: string, token: string) =>
  post<{ status: ClubAcceptStatus }>(`clubs/${userId}/invites/accept`, { token });

/** What a club link's fragment starts with, so the invite page knows it from the others. */
export const CLUB_LINK_PREFIX = "club:";

/** The full join link for a club token. */
export function clubInviteLink(token: string, origin = window.location.origin) {
  return `${origin}/invite#${CLUB_LINK_PREFIX}${token}`;
}
