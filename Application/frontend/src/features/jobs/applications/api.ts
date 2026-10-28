import { del, get, patch, post, put } from "../../../services/apiClient";
import { Application, ApplicationInput, ApplicationStats, Season, SeasonInput, StepInput } from "./types";

/** Base path of the user's applications. */
const base = (userId: string) => `jobs/${userId}/applications`;

/** One season's query string, ?season_id=…; empty for all time. */
const inSeason = (seasonId?: string | null) => (seasonId ? `?season_id=${seasonId}` : "");

/** Fetch applications, optionally one season's. */
export function fetchApplications(userId: string, seasonId?: string | null) {
  return get<Application[]>(`${base(userId)}${inSeason(seasonId)}`);
}

/** Figures and Sankey flows for one season, or all time. */
export function fetchApplicationStats(userId: string, seasonId?: string | null) {
  return get<ApplicationStats>(`${base(userId)}/stats${inSeason(seasonId)}`);
}

/** Fetch the user's recruiting seasons. */
export function fetchSeasons(userId: string) {
  return get<Season[]>(`${base(userId)}/seasons`);
}

/** Create a season. */
export function createSeason(userId: string, data: SeasonInput) {
  return post<Season>(`${base(userId)}/seasons`, data);
}

/** Replace a season's name and months. */
export function updateSeason(userId: string, id: string, data: SeasonInput) {
  return put<Season>(`${base(userId)}/seasons/${id}`, data);
}

/** Delete a season; no application goes with it. */
export function deleteSeason(userId: string, id: string) {
  return del<{ deleted: boolean }>(`${base(userId)}/seasons/${id}`);
}

/** Record a new application; its applied step is written with it. */
export function createApplication(userId: string, data: ApplicationInput) {
  return post<Application>(base(userId), data);
}

/** Edit an application's details. */
export function updateApplication(userId: string, id: string, data: Partial<ApplicationInput>) {
  return patch<Application>(`${base(userId)}/${id}`, data);
}

/** Delete an application and its whole history. */
export function deleteApplication(userId: string, id: string) {
  return del<{ deleted: boolean }>(`${base(userId)}/${id}`);
}

/** Record a status step; returns the updated application. */
export function addStep(userId: string, id: string, data: StepInput) {
  return post<Application>(`${base(userId)}/${id}/steps`, data);
}

/** Remove one step from an application's history. */
export function deleteStep(userId: string, id: string, stepId: string) {
  return del<Application>(`${base(userId)}/${id}/steps/${stepId}`);
}
