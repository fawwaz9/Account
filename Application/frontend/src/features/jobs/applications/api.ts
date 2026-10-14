import { del, get, patch, post, put } from "../../../services/apiClient";
import { Application, ApplicationInput, ApplicationStats, Season, SeasonInput, StepInput } from "./types";

const base = (userId: string) => `jobs/${userId}/applications`;

/** "?season_id=…" for one season (D7), or nothing for all time. */
const inSeason = (seasonId?: string | null) => (seasonId ? `?season_id=${seasonId}` : "");

export function fetchApplications(userId: string, seasonId?: string | null) {
  return get<Application[]>(`${base(userId)}${inSeason(seasonId)}`);
}

export function fetchApplicationStats(userId: string, seasonId?: string | null) {
  return get<ApplicationStats>(`${base(userId)}/stats${inSeason(seasonId)}`);
}

export function fetchSeasons(userId: string) {
  return get<Season[]>(`${base(userId)}/seasons`);
}

export function createSeason(userId: string, data: SeasonInput) {
  return post<Season>(`${base(userId)}/seasons`, data);
}

export function updateSeason(userId: string, id: string, data: SeasonInput) {
  return put<Season>(`${base(userId)}/seasons/${id}`, data);
}

export function deleteSeason(userId: string, id: string) {
  return del<{ deleted: boolean }>(`${base(userId)}/seasons/${id}`);
}

export function createApplication(userId: string, data: ApplicationInput) {
  return post<Application>(base(userId), data);
}

export function updateApplication(userId: string, id: string, data: Partial<ApplicationInput>) {
  return patch<Application>(`${base(userId)}/${id}`, data);
}

export function deleteApplication(userId: string, id: string) {
  return del<{ deleted: boolean }>(`${base(userId)}/${id}`);
}

export function addStep(userId: string, id: string, data: StepInput) {
  return post<Application>(`${base(userId)}/${id}/steps`, data);
}

export function deleteStep(userId: string, id: string, stepId: string) {
  return del<Application>(`${base(userId)}/${id}/steps/${stepId}`);
}
