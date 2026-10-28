import { del, get, post } from "../../services/apiClient";
import { AcceptStatus, NewInvite, Partners } from "./types";

/** Your figure, partners and open invites. */
export function fetchPartners(userId: string) {
  return get<Partners>(`partners/${userId}`);
}

/** Create a partner invite link; its token is shown once. */
export function createInvite(userId: string) {
  return post<NewInvite>(`partners/${userId}/invites`, {});
}

/** Cancel an invite link you sent; it simply stops working. */
export function revokeInvite(userId: string, inviteId: string) {
  return del<{ revoked: boolean }>(`partners/${userId}/invites/${inviteId}`);
}

/** Who sent a link; a POST, so the token stays out of URLs and logs. */
export function previewInvite(userId: string, token: string) {
  return post<{ inviter_name: string; kind: string }>(`partners/${userId}/invites/preview`, { token });
}

/** Accept a partner invite. */
export function acceptInvite(userId: string, token: string) {
  return post<{ status: AcceptStatus }>(`partners/${userId}/invites/accept`, { token });
}

/** End a partnership; the partner sees it has ended. */
export function endPartnership(userId: string, partnerId: string) {
  return del<{ ended: boolean }>(`partners/${userId}/partners/${partnerId}`);
}

/** The link to send: the token rides in the fragment, which never reaches a server. */
export function inviteLink(token: string, origin = window.location.origin) {
  return `${origin}/invite#${token}`;
}
