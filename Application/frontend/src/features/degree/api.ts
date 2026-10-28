import { del, get, post, put } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";

/** Where a counted course stands. */
export type Status = "completed" | "in_progress" | "planned";

/** A degree requirement the student entered. */
export interface Requirement {
  id: string;
  name: string;
  /** "courses" needs every item met; "credits" needs `credits_needed` from the items. */
  kind: "courses" | "credits";
  /** Course codes or patterns, e.g. "CPSC 110", "MATH 100 | MATH 180", "CPSC 3xx". */
  items: string[];
  /** Null for a "courses" requirement. */
  credits_needed: number | null;
  /** True lets a course counted here count toward other requirements too. */
  shares: boolean;
  /** Fill order among the student's requirements. */
  position: number;
}

/** A mapping that lets some courses count as others, e.g. a transfer course. */
export interface Equivalence {
  id: string;
  /** Courses that, all on the record, stand in for `counts_as`. */
  from_codes: string[];
  counts_as: string[];
  credits: number | null;
  note: string | null;
}

/** A course, or an equivalence standing in for courses, counted toward a requirement. */
export interface Counted {
  label: string;
  credits: number;
  status: Status;
}

/** One requirement audited: what meets it and its credit totals. */
export interface RequirementResult {
  requirement: Requirement;
  /** For "courses": each item and what meets it, null when nothing does yet. */
  items: { item: string; met_by: Counted | null }[];
  /** For "credits": everything counted, completed first. */
  counted: Counted[];
  credits_completed: number;
  credits_in_progress: number;
  credits_planned: number;
  /** Met with completed courses alone. */
  done: boolean;
}

/** The degree audit, computed on every read: each requirement's result and what's left over. */
export interface DegreeAudit {
  requirements: RequirementResult[];
  equivalences: Equivalence[];
  credits_completed: number;
  credits_in_progress: number;
  credit_target: number;
  /** Completed courses no requirement used: electives, or a missing mapping. */
  not_counted: Counted[];
  /** Courses that did not pass, which count nowhere. */
  failed: string[];
}

/** Request body for a requirement. */
export type RequirementBody = Omit<Requirement, "id" | "position">;
/** Request body for an equivalence. */
export type EquivalenceBody = Omit<Equivalence, "id">;

/** Run the degree audit. */
export const fetchAudit = (userId: string) => get<DegreeAudit>(endpoints.degree.audit(userId));
/** Add a degree requirement. */
export const createRequirement = (userId: string, body: RequirementBody) =>
  post<Requirement>(endpoints.degree.requirements(userId), body);
/** Replace a requirement's fields. */
export const updateRequirement = (userId: string, id: string, body: RequirementBody) =>
  put<Requirement>(endpoints.degree.requirement(userId, id), body);
/** Delete a requirement; callers confirm first. */
export const deleteRequirement = (userId: string, id: string) =>
  del<{ deleted: boolean }>(endpoints.degree.requirement(userId, id));
/** Add a course equivalence. */
export const createEquivalence = (userId: string, body: EquivalenceBody) =>
  post<Equivalence>(endpoints.degree.equivalences(userId), body);
/** Replace an equivalence's fields. */
export const updateEquivalence = (userId: string, id: string, body: EquivalenceBody) =>
  put<Equivalence>(endpoints.degree.equivalence(userId, id), body);
/** Delete an equivalence; callers confirm first. */
export const deleteEquivalence = (userId: string, id: string) =>
  del<{ deleted: boolean }>(endpoints.degree.equivalence(userId, id));
