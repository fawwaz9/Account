import { get } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";
import { Digest } from "./types";

/** Today's digest: calendar, work due, exams, risk, the week (Phase 4 item 6). */
export async function fetchDigest(userId: string) {
  return get<Digest>(endpoints.briefing.digest(userId));
}
