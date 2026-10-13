import { del, get, patch, post } from "../../../services/apiClient";
import { Application, ApplicationInput, ApplicationStats, StepInput } from "./types";

const base = (userId: string) => `jobs/${userId}/applications`;

export function fetchApplications(userId: string) {
  return get<Application[]>(base(userId));
}

export function fetchApplicationStats(userId: string) {
  return get<ApplicationStats>(`${base(userId)}/stats`);
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
