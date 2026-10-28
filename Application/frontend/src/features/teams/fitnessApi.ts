/** The Fitness page beyond teams (Phase 3 items 6-8 and 13): types and API calls under /api/fitness. */

import { get, put } from "../../services/apiClient";

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
