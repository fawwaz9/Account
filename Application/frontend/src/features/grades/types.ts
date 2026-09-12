// Course
export interface Course {
  id: string;
  code: string;
  name: string;
  year: number;
  semester: Semester;
  credits: number;
  required: boolean;
  professor: string | null;
  final_grade: number;
  /** null uses the account default from Settings */
  target_grade: number | null;
  category_weights: Partial<Record<GradeCategory, number>>;
  average: number;
  start_date: string | null;
  end_date: string | null;
  /** No final exam, so a missing final grade is not flagged in Attention. */
  no_final: boolean;
  /** Credit granted without taking the course: counts credits, carries no grade. */
  transfer_credit: boolean;
  /** Searchable and still in the average, but out of credits completed. */
  archived: boolean;
  /** Letter for the course's result; "" when nothing is recorded yet. */
  letter_grade: string;
  /** Grade points on the configured scale */
  grade_points: number;
  term_bucket: TermBucket;
}

export type TermBucket = "past" | "current" | "future";

export enum Semester {
  FALL = "Fall",
  WINTER = "Winter",
  SUMMER = "Summer",
  SPRING = "Spring"
}

export interface CourseCreate {
  code: string;
  name: string;
  semester: Semester;
  year: number;
  credits: number;
  required: boolean;
  professor: string | null;
  final_grade: number;
  /** The grade you are aiming for; null falls back to the account default */
  target_grade: number | null;
  category_weights: Partial<Record<GradeCategory, number>>;
  // ISO yyyy-mm-dd, or null for a course with no set term dates
  start_date: string | null;
  end_date: string | null;
  /** No final exam, so a missing final grade is not flagged in Attention. */
  no_final: boolean;
  /** Credit granted without taking the course: counts credits, carries no grade. */
  transfer_credit: boolean;
  /** Searchable and still in the average, but out of credits completed. */
  archived: boolean;
}

export interface CourseDetail {
  id: string;
  code: string;
  name: string;
  year: number;
  semester: Semester;
  credits: number;
  required: boolean;
  professor: string | null;
  final_grade: number;
  category_weights: Partial<Record<GradeCategory, number>>;
  average: number;
  target_grade: number | null;
  letter_grade: string;
  grade_points: number;
  grades: Grade[];
  start_date: string | null;
  end_date: string | null;
  /** No final exam, so a missing final grade is not flagged in Attention. */
  no_final: boolean;
  /** Credit granted without taking the course: counts credits, carries no grade. */
  transfer_credit: boolean;
  /** Searchable and still in the average, but out of credits completed. */
  archived: boolean;
  // Point-weighted average per category, computed by the API. Render these
  // rather than recomputing -- the component used to do its own arithmetic and
  // disagreed with the course average on the same screen.
  category_averages: Partial<Record<GradeCategory, number>>;
}

export interface CourseUpdate{
  code: string | null;
  name: string | null;
  semester: Semester | null;
  year: number | null;
  credits: number | null;
  required: boolean | null;
  professor: string | null;
  final_grade: number | null;
  target_grade: number | null;
  category_weights: Partial<Record<GradeCategory, number>> | null;
  start_date: string | null;
  end_date: string | null;
  no_final: boolean | null;
  transfer_credit: boolean | null;
  archived: boolean | null;
}


// Grade
export interface Grade {
  id: string;
  name: string;
  // null until the assignment has been marked
  score: number | null;
  max_score: number;
  category: GradeCategory;
  weight: number;
  /** When the work is due, as opposed to when it was marked. */
  due_date: string | null;
  /** What that date means. Ignored when there is no date. */
  schedule_as: GradeSchedule;
  /** Kept on the course but left out of every average, e.g. a dropped quiz. */
  excluded: boolean;
}

/**
 * How a dated grade shows up outside the gradebook.
 *
 * Two different things wear a date: an assignment due Friday is work you tick
 * off, a midterm on the 15th is something you sit. Forcing both through a task
 * made the second read as a chore that never quite closes.
 */
export enum GradeSchedule {
  /** Raises a task that closes itself when the score lands. */
  TASK = "task",
  /** Draws a block on the calendar and nothing else. */
  EVENT = "event",
}

export enum GradeCategory {
  ASSIGNMENT = "Assignment",
  LAB = "Lab",
  QUIZ = "Quiz",
  MIDTERM = "Midterm",
  PARTICIPATION = "Participation",
  PROJECT = "Project",
  OTHER = "Other",
  FINAL = "Final",
  /** Adds to the course average rather than forming part of it. See bonus.ts. */
  BONUS = "Bonus"
}

/**
 * Where a course can still finish.
 *
 * A running average cannot answer this: 78% with everything marked is a result,
 * 78% with the final still to come is anywhere between a fail and an A.
 */
export interface GradeBand {
  /** Every outstanding item at full marks. */
  best: number;
  /** Every outstanding item at nothing. */
  worst: number;
  /** The live average, which sits between them. */
  current: number;
  /** Nothing left to mark, so best and worst have met. */
  settled: boolean;
  outstanding_items: number;
  /** Weighted categories with nothing entered at all. */
  empty_categories: string[];
}

/** Answer from the "what do I need on the final" calculation. */
export interface RequiredFinal {
  /** Score needed on the final, as a percentage. Can fall outside 0-100. */
  needed: number;
  /** False when `needed` is unreachable — above 100 or already below 0. */
  possible: boolean;
  /** Weighted categories with no marks yet, which the figure does not count. */
  unfinished_categories: string[];
}

export interface CategoryWeightsUpdate {
  category_weights: Partial<Record<GradeCategory, number>>;
}

export interface GradeCreate{
  name: string;
  // omit or send null to add an assignment that is not graded yet
  score: number | null;
  max_score: number;
  category: GradeCategory;
  due_date: string | null;
  schedule_as: GradeSchedule;
}

export interface GradeUpdate{
  name: string | null;
  score: number | null;
  max_score: number | null;
  category: GradeCategory | null;
  due_date: string | null;
  schedule_as: GradeSchedule | null;
  /** Kept on the course but left out of every average. */
  excluded: boolean | null;
}


// Error Handling
export interface HTTPValidationError {
  detail: ValidationError[];
}

export interface ValidationError {
  loc: (string | number)[];
  msg: string;
  type: string;
  input: unknown;
  ctx?: Record<string, unknown>;
}


// User
export interface User {
  id: string;
  name: string;
  email: string;
}

export interface UserCreate {
  name: string;
  email: string;
  // add current_semester in the future
}

export interface UserDetail {
  id: string;
  name: string;
  email: string;
  courses: Course[];
}

export interface UserUpdate{
  name: string | null;
  email: string | null;
}


// Dashboard
export interface YearSummary {
  school_year: number;
  /** null when no course that year has anything recorded */
  average: number | null;
  course_count: number;
}

export type AttentionKind = "missing_final" | "below_target" | "weight_problem";

export interface AttentionItem {
  kind: AttentionKind;
  course_id: string;
  course_code: string;
  message: string;
}

export interface TermPoint {
  school_year: number;
  semester: string;
  label: string;
  /** Plain mean across that term's courses */
  term_average: number;
  /** Credit-weighted cumulative up to that term; null until a course has a final */
  cumulative_average: number | null;
}

export interface UserGradeDashboard {
  total_courses: number;
  /** Credit-weighted mean */
  cumulative_average: number;
  /** Plain mean across the current term only */
  semester_average: number;
  /** null when the GPA scale is switched off in settings */
  cgpa: number | null;
  credits_completed: number;
  credits_in_progress: number;
  credits_required: number;
  credits_elective: number;
  credit_target: number;
  attention: AttentionItem[];
  term_history: TermPoint[];
  past_years: YearSummary[];
  future_years: YearSummary[];
  best_course: CourseDashboardEntry | null;
  weakest_course: CourseDashboardEntry | null;
  courses_needing_final_score: CourseNeedingFinalScore[];
  unfinished_categories_by_course: Record<string, string[]>;
}

export interface CourseDashboardEntry {
  course_id: string;
  course_code: string;
  course_name: string;
  average: number;
  needed_final_score: number | null;
  unfinished_categories: string[];
}

export interface CourseNeedingFinalScore {
  course_id: string;
  course_code: string;
  course_name: string;
  average: number;
  needed_final_score: number | null;
  unfinished_categories: string[];
}