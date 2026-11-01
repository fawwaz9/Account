/** The digest of a student's day (Phase 4 item 6). No money in it (D8). */
export interface Digest {
  on_date: string;
  events: { title: string; kind: string; start_time: string | null; end_time: string | null;
    location: string | null; course_code: string | null }[];
  due_today: DigestTask[];
  overdue: DigestTask[];
  overdue_count: number;
  exams: { name: string; on_date: string; days_left: number; open_tasks: number; estimated_minutes: number }[];
  at_risk: { due_date: string; titles: string[]; shortfall_minutes: number }[];
  week: { booked_minutes: number; estimated_minutes: number; tasks_due: number };
  free_minutes_today: number;
  longest_free_start: string | null;
  longest_free_minutes: number;
  /** The whole digest in plain sentences, one line per part; the first line is the date. */
  text: string;
}

/** A task due today or overdue. */
export interface DigestTask {
  title: string;
  course_code: string | null;
  due_date: string | null;
  due_time: string | null;
  estimated_minutes: number | null;
}
