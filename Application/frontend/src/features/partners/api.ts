import { del, get, post } from "../../services/apiClient";
import { AcceptStatus, NewInvite, Partners } from "./types";

export function fetchPartners(userId: string) {
  return get<Partners>(`partners/${userId}`);
}

export function createInvite(userId: string) {
  return post<NewInvite>(`partners/${userId}/invites`, {});
}

/** Cancel a link you sent. Not a delete of anything of anyone's: it only stops working. */
export function revokeInvite(userId: string, inviteId: string) {
  return del<{ revoked: boolean }>(`partners/${userId}/invites/${inviteId}`);
}

/** Who sent a link. POST, so the token stays out of URLs and logs. */
export function previewInvite(userId: string, token: string) {
  return post<{ inviter_name: string; kind: string }>(`partners/${userId}/invites/preview`, { token });
}

export function acceptInvite(userId: string, token: string) {
  return post<{ status: AcceptStatus }>(`partners/${userId}/invites/accept`, { token });
}

export function endPartnership(userId: string, partnerId: string) {
  return del<{ ended: boolean }>(`partners/${userId}/partners/${partnerId}`);
}

/** The link to send: the token rides in the fragment, which browsers never send to a server. */
export function inviteLink(token: string, origin = window.location.origin) {
  return `${origin}/invite#${token}`;
}
