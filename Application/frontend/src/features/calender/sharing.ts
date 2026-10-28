import { del, get, post } from "../../services/apiClient";
import type { Sharing } from "../../shared/components/SharingSection";

/** Someone else's event you are on: when and where, and who else is on it. */
export interface SharedEvent {
  event_id: string;
  owner_name: string;
  title: string;
  kind: string;
  location: string | null;
  notes: string | null;
  starts_on: string;
  start_time: string | null;
  end_time: string | null;
  /** Everyone on it besides the owner, you included. */
  member_names: string[];
}

/** Outcome of accepting an event invite link. */
export type EventAcceptStatus = "accepted" | "invalid" | "own" | "already" | "full";

// --- the owner ---------------------------------------------------------------

/** Load who is on one of your events and whether a link is open. */
export function fetchEventSharing(userId: string, eventId: string) {
  return get<Sharing>(`calendar/${userId}/events/${eventId}/sharing`);
}

/** Open a new invite link for your event; an older link stops working. */
export function makeEventLink(userId: string, eventId: string) {
  return post<{ token: string; expires_at: string }>(`calendar/${userId}/events/${eventId}/sharing/link`, {});
}

/** Cancel your event's open invite link. */
export function cancelEventLink(userId: string, eventId: string) {
  return del<{ cancelled: boolean }>(`calendar/${userId}/events/${eventId}/sharing/link`);
}

/** Take one member off your event. */
export function removeEventMember(userId: string, eventId: string, memberId: string) {
  return del<{ removed: boolean }>(`calendar/${userId}/events/${eventId}/sharing/members/${memberId}`);
}

// --- the member --------------------------------------------------------------

/** Events others share with you that fall between `start` and `end`. */
export function fetchSharedEvents(userId: string, start: string, end: string) {
  return get<SharedEvent[]>(`calendar/${userId}/shared-events?start=${start}&end=${end}`);
}

/** Take yourself off someone else's event; their event is untouched. */
export function leaveSharedEvent(userId: string, eventId: string) {
  return del<{ left: boolean }>(`calendar/${userId}/shared-events/${eventId}`);
}

/** Look up the event an invite token is for, without joining it. */
export function previewEventInvite(userId: string, token: string) {
  return post<{ owner_name: string; title: string; starts_on: string }>(
    `calendar/${userId}/shared-events/invites/preview`, { token });
}

/** Join an event through an invite token. */
export function acceptEventInvite(userId: string, token: string) {
  return post<{ status: EventAcceptStatus }>(`calendar/${userId}/shared-events/invites/accept`, { token });
}

/** Fragment prefix marking an invite link as an event's. */
export const EVENT_LINK_PREFIX = "event:";

/** The invite URL to send; the token rides in the fragment, which never reaches a server. */
export function eventInviteLink(token: string, origin = window.location.origin) {
  return `${origin}/invite#${EVENT_LINK_PREFIX}${token}`;
}
