import { get, getBlob, post } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";
import { GradeCategory } from "../grades/types";

export interface Assessment {
  name: string;
  category: GradeCategory;
  /** Percent of the course grade, for all of them together when count > 1. */
  weight: number;
  count: number;
  due_date: string | null;
  date_tba: boolean;
}

/** Prerequisites as the syllabus states them (Phase 2 item 5). `text` is the
 *  rule in the typed form, empty when the reader couldn't make one; `sentence`
 *  is the syllabus's own words, which stay with you. */
export interface ExtractedRule {
  rule: Record<string, unknown> | null;
  text: string;
  note: string | null;
  sentence: string | null;
}

/** A rule as confirmed on the check screen. Left out, nothing is filed. */
export interface ConfirmedRule {
  text: string;
  note: string | null;
}

export interface SyllabusExtract {
  course_code: string;
  course_name: string;
  section?: string | null;
  professor: string | null;
  assessments: Assessment[];
  multiple_schemes: boolean;
  prerequisites?: ExtractedRule | null;
  corequisites?: ExtractedRule | null;
}

export interface ParseResult {
  id: string;
  extract: SyllabusExtract;
  warnings: string[];
  created_at: string;
}

export interface ApplyResult {
  course_id: string;
  grades_created: number;
  fields_total: number;
  fields_changed: number;
}

export function intakeStatus(userId: string) {
  return get<{ available: boolean }>(endpoints.intake.status(userId));
}

export function readSyllabus(userId: string, filename: string, mediaType: string, contentBase64: string) {
  return post<ParseResult>(endpoints.intake.syllabus(userId), {
    filename, media_type: mediaType, content_base64: contentBase64,
  });
}

export function applySyllabus(
  userId: string,
  parseId: string,
  body: { course_code: string; course_name: string; section: string | null; professor: string | null; credits: number;
    assessments: Assessment[]; prerequisites?: ConfirmedRule; corequisites?: ConfirmedRule },
) {
  return post<ApplyResult>(endpoints.intake.apply(userId, parseId), body);
}

export interface KeptSyllabus {
  id: string;
  filename: string | null;
  media_type: string | null;
  created_at: string;
}

export function fetchCourseSyllabi(userId: string, courseId: string) {
  return get<KeptSyllabus[]>(endpoints.intake.courseSyllabi(userId, courseId));
}

export function fetchSyllabusFile(userId: string, parseId: string) {
  return getBlob(endpoints.intake.file(userId, parseId));
}

/* ===== Adding to a course you already have (Phase 1 D27) ===== */

export interface ProposedRow {
  name: string;
  category: GradeCategory;
  due_date: string | null;
  /** The course already has this: shown, never added. */
  exists: boolean;
  matched: string | null;
}

export interface AddPreview {
  rows: ProposedRow[];
  weight_notes: { category: GradeCategory; syllabus: number; course: number }[];
  unweighted: GradeCategory[];
  section_offer: string | null;
  prerequisites?: ExtractedRule | null;
  corequisites?: ExtractedRule | null;
  /** Your own rule for the course now, which confirming would replace. */
  own_prerequisites?: string | null;
  own_corequisites?: string | null;
}

export interface AddResult {
  added: number;
  skipped: number;
  section_set: boolean;
  rules_filed?: number;
}

export function previewAdd(userId: string, parseId: string, courseId: string) {
  return get<AddPreview>(endpoints.intake.addTo(userId, parseId, courseId));
}

export function addToCourse(
  userId: string, parseId: string, courseId: string,
  body: { rows: { name: string; category: GradeCategory; due_date: string | null }[]; set_section: boolean;
    prerequisites?: ConfirmedRule; corequisites?: ConfirmedRule },
) {
  return post<AddResult>(endpoints.intake.addTo(userId, parseId, courseId), body);
}

