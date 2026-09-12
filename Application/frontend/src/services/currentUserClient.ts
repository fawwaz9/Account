import { get, patch } from "./apiClient";
import { endpoints } from "./endpoints";

export interface CurrentUser {
  id: string;
  name: string;
  email: string;
  auth_provider: "google" | "local";
  email_verified: boolean;
  /** Can sign in with email + password */
  has_password: boolean;
  /** Can sign in with Google */
  has_google: boolean;
  /** Null until set; while unset every course reads as current */
  current_school_year: number | null;
  current_semester: string | null;
  term_label: string | null;
  preferences: {
    credit_target: number;
    gpa_scale_enabled: boolean;
    default_target_grade: number;
    /** "HH:MM:SS" — the hours free blocks are offered in. */
    study_day_start: string;
    study_day_end: string;
    /** Below this a gap is walking time, not study time. */
    min_free_block_minutes: number;
    [key: string]: unknown;
  };
}

export async function getCurrentUser(): Promise<CurrentUser> {
  return get<CurrentUser>(endpoints.users.me);
}
export interface AcademicStatusUpdate {
  school_year?: number;
  semester?: string;
  term_label?: string | null;
}

/** Set the term the student is in; drives past/current/future everywhere. */
export function updateAcademicStatus(userId: string, status: AcademicStatusUpdate) {
  return patch<CurrentUser>(endpoints.users.academicStatus(userId), status);
}

/** Partial preference update; the server merges rather than replacing. */
export function updatePreferences(userId: string, preferences: Record<string, unknown>) {
  return patch<CurrentUser>(endpoints.users.detail(userId), { preferences });
}
