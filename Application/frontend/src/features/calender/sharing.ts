import { del, get, post } from "../../services/apiClient";
import type { Sharing } from "../../shared/components/SharingSection";

/** Someone else's event you are on (Phase 2 item 9b, D24): when and where. */
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

export type EventAcceptStatus = "accepted" | "invalid" | "own" | "already" | "full";

// --- the owner ---------------------------------------------------------------

export function fetchEventSharing(userId: string, eventId: string) {
  return get<Sharing>(`calendar/${userId}/events/${eventId}/sharing`);
}

export function makeEventLink(userId: string, eventId: string) {
  return post<{ token: string; expires_at: string }>(`calendar/${userId}/events/${eventId}/sharing/link`, {});
}

export function cancelEventLink(userId: string, eventId: string) {
  return del<{ cancelled: boolean }>(`calendar/${userId}/events/${eventId}/sharing/link`);
}

export function removeEventMember(userId: string, eventId: string, memberId: string) {
  return del<{ removed: boolean }>(`calendar/${userId}/events/${eventId}/sharing/members/${memberId}`);
}

// --- the member --------------------------------------------------------------

export function fetchSharedEvents(userId: string, start: string, end: string) {
  return get<SharedEvent[]>(`calendar/${userId}/shared-events?start=${start}&end=${end}`);
}

/** Take yourself off someone else's event. Their event is untouched. */
export function leaveSharedEvent(userId: string, eventId: string) {
  return del<{ left: boolean }>(`calendar/${userId}/shared-events/${eventId}`);
}

export function previewEventInvite(userId: string, token: string) {
  return post<{ owner_name: string; title: string; starts_on: string }>(
    `calendar/${userId}/shared-events/invites/preview`, { token });
}

export function acceptEventInvite(userId: string, token: string) {
  return post<{ status: EventAcceptStatus }>(`calendar/${userId}/shared-events/invites/accept`, { token });
}

export const EVENT_LINK_PREFIX = "event:";

/** The link to send: the token rides in the fragment, which browsers never send to a server. */
export function eventInviteLink(token: string, origin = window.location.origin) {
  return `${origin}/invite#${EVENT_LINK_PREFIX}${token}`;
}
