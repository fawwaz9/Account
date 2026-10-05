import { get, post } from "../../services/apiClient";
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

export interface SyllabusExtract {
  course_code: string;
  course_name: string;
  section?: string | null;
  professor: string | null;
  assessments: Assessment[];
  multiple_schemes: boolean;
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
    assessments: Assessment[] },
) {
  return post<ApplyResult>(endpoints.intake.apply(userId, parseId), body);
}
