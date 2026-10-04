import type { EventKind } from "../features/calender/types";
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
  /**
   * The calendar year first year began. A school year is 1..10, so this is
   * what turns "Fall of year 3" into real dates. Null means terms have none,
   * and anything measuring one says so rather than guessing.
   */
  first_year_calendar_year: number | null;
  /**
   * What the anchor looks like from the courses that already carry dates.
   * Derived on read, never stored, and deliberately not taken from term_label
   * -- that is free text nothing keeps current, and on a real account it reads
   * a year behind the courses it describes.
   */
  suggested_first_year: number | null;
  preferences: {
    /**
     * IANA zone. Declared rather than left to the index signature below, because
     * it is read at a call site that would otherwise get `unknown` -- and because
     * it is the one preference in this object that changes behaviour rather than
     * presentation: reminders fire on it, and so does whether a task counts as
     * finished early or late.
     */
    timezone: string;
    credit_target: number;
    gpa_scale_enabled: boolean;
    default_target_grade: number;
    /** "HH:MM:SS" — the hours free blocks are offered in. */
    study_day_start: string;
    study_day_end: string;
    /** Below this a gap is walking time, not study time. */
    min_free_block_minutes: number;
    /**
     * Colour per event kind, only for the kinds the student changed. A missing
     * kind means its default (features/calender/kindColors.ts).
     */
    event_colors?: Partial<Record<EventKind, string>>;
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
  first_year_calendar_year?: number | null;
}

/** Set the term the student is in; drives past/current/future everywhere. */
export function updateAcademicStatus(userId: string, status: AcademicStatusUpdate) {
  return patch<CurrentUser>(endpoints.users.academicStatus(userId), status);
}

/** Partial preference update; the server merges rather than replacing. */
export function updatePreferences(userId: string, preferences: Record<string, unknown>) {
  return patch<CurrentUser>(endpoints.users.detail(userId), { preferences });
}
