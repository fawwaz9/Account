import { del, get, post, put } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";

export type Status = "completed" | "in_progress" | "planned";

export interface Requirement {
  id: string;
  name: string;
  kind: "courses" | "credits";
  items: string[];
  credits_needed: number | null;
  shares: boolean;
  position: number;
}

export interface Equivalence {
  id: string;
  from_codes: string[];
  counts_as: string[];
  credits: number | null;
  note: string | null;
}

export interface Counted {
  label: string;
  credits: number;
  status: Status;
}

export interface RequirementResult {
  requirement: Requirement;
  items: { item: string; met_by: Counted | null }[];
  counted: Counted[];
  credits_completed: number;
  credits_in_progress: number;
  credits_planned: number;
  done: boolean;
}

export interface DegreeAudit {
  requirements: RequirementResult[];
  equivalences: Equivalence[];
  credits_completed: number;
  credits_in_progress: number;
  credit_target: number;
  not_counted: Counted[];
  failed: string[];
}

export type RequirementBody = Omit<Requirement, "id" | "position">;
export type EquivalenceBody = Omit<Equivalence, "id">;

export const fetchAudit = (userId: string) => get<DegreeAudit>(endpoints.degree.audit(userId));
export const createRequirement = (userId: string, body: RequirementBody) =>
  post<Requirement>(endpoints.degree.requirements(userId), body);
export const updateRequirement = (userId: string, id: string, body: RequirementBody) =>
  put<Requirement>(endpoints.degree.requirement(userId, id), body);
/** Permanent, so it is confirmed first. */
export const deleteRequirement = (userId: string, id: string) =>
  del<{ deleted: boolean }>(endpoints.degree.requirement(userId, id));
export const createEquivalence = (userId: string, body: EquivalenceBody) =>
  post<Equivalence>(endpoints.degree.equivalences(userId), body);
export const updateEquivalence = (userId: string, id: string, body: EquivalenceBody) =>
  put<Equivalence>(endpoints.degree.equivalence(userId, id), body);
/** Permanent, so it is confirmed first. */
export const deleteEquivalence = (userId: string, id: string) =>
  del<{ deleted: boolean }>(endpoints.degree.equivalence(userId, id));
