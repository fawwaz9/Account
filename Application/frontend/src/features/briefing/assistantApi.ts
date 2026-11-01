import { del, get, post } from "../../services/apiClient";

/** Whether you have an assistant token, and what to recognise it by. Never the token (Phase 4 item 7). */
export interface AssistantTokenStatus {
  enabled: boolean;
  prefix: string | null;
  created_at: string | null;
  last_used_at: string | null;
}

/** A new token: the only time it is shown. */
export interface AssistantTokenMade {
  token: string;
  prefix: string;
  created_at: string;
}

export const fetchAssistantToken = (userId: string) =>
  get<AssistantTokenStatus>(`briefing/${userId}/assistant-token`, { fresh: true });

export const makeAssistantToken = (userId: string) => post<AssistantTokenMade>(`briefing/${userId}/assistant-token`, {});

export const revokeAssistantToken = (userId: string) => del<void>(`briefing/${userId}/assistant-token`);
