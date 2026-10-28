import type { EventKind } from "../features/calender/types";
import { get, patch } from "./apiClient";
import { endpoints } from "./endpoints";

/** The signed-in user from `users/me`, with their preferences. */
export interface CurrentUser {
  id: string;
  name: string;
  email: string;
  auth_provider: "google" | "local";
  email_verified: boolean;
  /** Can sign in with email and password. */
  has_password: boolean;
  /** Can sign in with Google. */
  has_google: boolean;
  /** School year 1-10; null until set, and then every course reads as current. */
  current_school_year: number | null;
  /** Term name, e.g. "Fall"; null until set. */
  current_semester: string | null;
  /** Free text the student typed; nothing keeps it current. */
  term_label: string | null;
  /** First-year anchor: the calendar year school year 1 began; null leaves terms undated. */
  first_year_calendar_year: number | null;
  /** Anchor implied by courses that already carry dates; derived on read. */
  suggested_first_year: number | null;
  preferences: {
    /** IANA zone; sets the user's today and when reminders fire. */
    timezone: string;
    credit_target: number;
    gpa_scale_enabled: boolean;
    /** Percent target given to a new course. */
    default_target_grade: number;
    /** "HH:MM:SS" start of the hours free blocks are offered in. */
    study_day_start: string;
    /** "HH:MM:SS" end of those hours. */
    study_day_end: string;
    /** Gaps shorter than this are not offered as study time. */
    min_free_block_minutes: number;
    /** A shift ending within this many hours before an exam is flagged. */
    exam_buffer_hours?: number;
    /** Colour per event kind the student changed; a missing kind uses its default. */
    event_colors?: Partial<Record<EventKind, string>>;
    /** Account cash tips are filed to; null or absent holds them on the shift. */
    cash_tip_account_id?: string | null;
    /** Count your categories toward the shared merchant map; absent means on. */
    share_merchant_categories?: boolean;
    [key: string]: unknown;
  };
}

/** Fetch the signed-in user. */
export async function getCurrentUser(): Promise<CurrentUser> {
  return get<CurrentUser>(endpoints.users.me);
}
/** Patch body for the school year, term, label and first-year anchor. */
export interface AcademicStatusUpdate {
  school_year?: number;
  semester?: string;
  term_label?: string | null;
  first_year_calendar_year?: number | null;
}

/** Set the student's school year, term or anchor; drives every term bucket. */
export function updateAcademicStatus(userId: string, status: AcademicStatusUpdate) {
  return patch<CurrentUser>(endpoints.users.academicStatus(userId), status);
}

/** Patch some preferences; the server merges them into the stored set. */
export function updatePreferences(userId: string, preferences: Record<string, unknown>) {
  return patch<CurrentUser>(endpoints.users.detail(userId), { preferences });
}
