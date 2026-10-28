import { get, getBlob, post } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";
import { GradeCategory } from "../grades/types";

/** One graded item as read from a syllabus. */
export interface Assessment {
  name: string;
  category: GradeCategory;
  /** Percent of the course grade, for all `count` of them together. */
  weight: number;
  /** How many there are: ten weekly quizzes is one line with count 10. */
  count: number;
  due_date: string | null;
  /** Known to exist but not yet scheduled, as a final usually is. */
  date_tba: boolean;
}

/**
 * A requisite as the syllabus states it: `text` in the typed form ("" when unreadable),
 * `sentence` in the syllabus's own words.
 */
export interface ExtractedRule {
  rule: Record<string, unknown> | null;
  text: string;
  note: string | null;
  sentence: string | null;
}

/** A rule confirmed on the check screen; when left out, nothing is filed. */
export interface ConfirmedRule {
  text: string;
  note: string | null;
}

/** What the reader took from a syllabus, for the student to check before anything is saved. */
export interface SyllabusExtract {
  course_code: string;
  course_name: string;
  section?: string | null;
  professor: string | null;
  assessments: Assessment[];
  /** The syllabus offers more than one grading scheme. */
  multiple_schemes: boolean;
  prerequisites?: ExtractedRule | null;
  corequisites?: ExtractedRule | null;
}

/** A stored syllabus parse: its extract and the reader's warnings. */
export interface ParseResult {
  id: string;
  extract: SyllabusExtract;
  warnings: string[];
  created_at: string;
}

/** The course a checked syllabus created, and how much of the parse was edited. */
export interface ApplyResult {
  course_id: string;
  grades_created: number;
  /** Fields in the parse; with `fields_changed`, how much the student edited before confirming. */
  fields_total: number;
  fields_changed: number;
}

/** Whether syllabus reading is configured on the server. */
export function intakeStatus(userId: string) {
  return get<{ available: boolean }>(endpoints.intake.status(userId));
}

/** Send a syllabus file, base64, to be read; returns the parse to check. */
export function readSyllabus(userId: string, filename: string, mediaType: string, contentBase64: string) {
  return post<ParseResult>(endpoints.intake.syllabus(userId), {
    filename, media_type: mediaType, content_base64: contentBase64,
  });
}

/** Create a course from a checked syllabus parse. */
export function applySyllabus(
  userId: string,
  parseId: string,
  body: { course_code: string; course_name: string; section: string | null; professor: string | null; credits: number;
    assessments: Assessment[]; prerequisites?: ConfirmedRule; corequisites?: ConfirmedRule },
) {
  return post<ApplyResult>(endpoints.intake.apply(userId, parseId), body);
}

/** A syllabus file kept on a course. */
export interface KeptSyllabus {
  id: string;
  filename: string | null;
  media_type: string | null;
  created_at: string;
}

/** The syllabus files kept on a course. */
export function fetchCourseSyllabi(userId: string, courseId: string) {
  return get<KeptSyllabus[]>(endpoints.intake.courseSyllabi(userId, courseId));
}

/** Download a kept syllabus file as a Blob. */
export function fetchSyllabusFile(userId: string, parseId: string) {
  return getBlob(endpoints.intake.file(userId, parseId));
}

/* ===== Adding to a course you already have (Phase 1 D27) ===== */

/** One gradebook row a syllabus implies for an existing course. */
export interface ProposedRow {
  name: string;
  category: GradeCategory;
  due_date: string | null;
  /** The course already has this: shown, never added. */
  exists: boolean;
  /** The existing row it matched, when it exists. */
  matched: string | null;
}

/** What adding a syllabus to an existing course would do. */
export interface AddPreview {
  rows: ProposedRow[];
  /** Weights the syllabus states that differ from the course's; adding never changes one. */
  weight_notes: { category: GradeCategory; syllabus: number; course: number }[];
  /** Categories new rows would go into that the course weights at 0%. */
  unweighted: GradeCategory[];
  /** The syllabus's section, offered only when the course has none. */
  section_offer: string | null;
  prerequisites?: ExtractedRule | null;
  corequisites?: ExtractedRule | null;
  /** Your own rule for the course now, which confirming would replace. */
  own_prerequisites?: string | null;
  own_corequisites?: string | null;
}

/** What adding a syllabus to a course did. */
export interface AddResult {
  added: number;
  /** Rows the course already had by the time they arrived. */
  skipped: number;
  section_set: boolean;
  rules_filed?: number;
}

/** Preview adding a parsed syllabus to an existing course. */
export function previewAdd(userId: string, parseId: string, courseId: string) {
  return get<AddPreview>(endpoints.intake.addTo(userId, parseId, courseId));
}

/** Add confirmed rows, and optionally the section and rules, to an existing course. */
export function addToCourse(
  userId: string, parseId: string, courseId: string,
  body: { rows: { name: string; category: GradeCategory; due_date: string | null }[]; set_section: boolean;
    prerequisites?: ConfirmedRule; corequisites?: ConfirmedRule },
) {
  return post<AddResult>(endpoints.intake.addTo(userId, parseId, courseId), body);
}

