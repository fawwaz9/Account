// Course
/** One place a course lives online: Canvas, Piazza, a syllabus. */
export interface CourseLink {
  title: string;
  url: string;
}

/** A course as listed, with its server-computed average, letter, points and term bucket. */
export interface Course {
  /** Grading scheme counted as the course's grade; null or absent uses its own weights. */
  counting_scheme_id?: string | null;
  id: string;
  code: string;
  name: string;
  year: number;
  semester: Semester;
  credits: number;
  required: boolean;
  professor: string | null;
  /** The student's section, e.g. "101"; a syllabus belongs to one section. */
  section: string | null;
  /** Recorded final percentage; 0 means none recorded. */
  final_grade: number;
  /** Server-set projection from just before the final was marked; null when there was none. */
  projected_before_final?: number | null;
  /** Day `projected_before_final` was taken, YYYY-MM-DD. */
  projected_on?: string | null;
  /** Target percentage; null uses the Settings default. */
  target_grade: number | null;
  category_weights: Partial<Record<GradeCategory, number>>;
  /** Average of marked work only; null when nothing is marked, never 0. */
  average: number | null;
  start_date: string | null;
  end_date: string | null;
  /** No final exam, so a missing final grade is never flagged in Attention. */
  no_final: boolean;
  /** Credit granted without taking the course: counts credits, carries no grade. */
  transfer_credit: boolean;
  /** Still searchable and in the average, but out of credits completed. */
  archived: boolean;
  /** Where the course lives, in display order; always sent and saved whole. */
  links: CourseLink[];
  /** Letter for the course's grade; "" when nothing is recorded yet. */
  letter_grade: string;
  /** Grade points on the configured scale. */
  grade_points: number;
  term_bucket: TermBucket;
}

/** Where a course's term sits against the student's current term. */
export type TermBucket = "past" | "current" | "future";

/** Term names as the API spells them. */
export enum Semester {
  FALL = "Fall",
  WINTER = "Winter",
  SUMMER = "Summer",
  SPRING = "Spring"
}

/** Request body for creating a course. */
export interface CourseCreate {
  code: string;
  name: string;
  semester: Semester;
  year: number;
  credits: number;
  required: boolean;
  professor: string | null;
  /** The student's section, e.g. "101"; a syllabus belongs to one section. */
  section: string | null;
  /** Recorded final percentage; 0 means none recorded. */
  final_grade: number;
  /** Target percentage; null uses the Settings default. */
  target_grade: number | null;
  category_weights: Partial<Record<GradeCategory, number>>;
  /** YYYY-MM-DD; null when the course has no set term dates. */
  start_date: string | null;
  end_date: string | null;
  /** No final exam, so a missing final grade is never flagged in Attention. */
  no_final: boolean;
  /** Credit granted without taking the course: counts credits, carries no grade. */
  transfer_credit: boolean;
  /** Still searchable and in the average, but out of credits completed. */
  archived: boolean;
  /** Where the course lives, in display order; always sent and saved whole. */
  links: CourseLink[];
}

/** One course with its grades and per-category figures, as the course page reads it. */
export interface CourseDetail {
  /** Grading scheme counted as the course's grade; null or absent uses its own weights. */
  counting_scheme_id?: string | null;
  id: string;
  code: string;
  name: string;
  year: number;
  semester: Semester;
  credits: number;
  required: boolean;
  professor: string | null;
  /** The student's section, e.g. "101"; a syllabus belongs to one section. */
  section: string | null;
  /** Recorded final percentage; 0 means none recorded. */
  final_grade: number;
  category_weights: Partial<Record<GradeCategory, number>>;
  /** Null when nothing is marked; see `Course.average`. */
  average: number | null;
  target_grade: number | null;
  letter_grade: string;
  grade_points: number;
  grades: Grade[];
  start_date: string | null;
  end_date: string | null;
  /** No final exam, so a missing final grade is never flagged in Attention. */
  no_final: boolean;
  /** Credit granted without taking the course: counts credits, carries no grade. */
  transfer_credit: boolean;
  /** Still searchable and in the average, but out of credits completed. */
  archived: boolean;
  term_bucket: TermBucket;
  /** Where the course lives, in display order; always sent and saved whole. */
  links: CourseLink[];
  /** Server-computed average per category, 0-100; render as sent, never recompute. */
  category_averages: Partial<Record<GradeCategory, number>>;
  /** Marks each category contributes out of its weight; sent because deriving it rounds twice. */
  category_points: Partial<Record<GradeCategory, number>>;
}

/** Patch body for a course; callers send a `Partial` holding only the changed fields. */
export interface CourseUpdate{
  code: string | null;
  name: string | null;
  semester: Semester | null;
  year: number | null;
  credits: number | null;
  required: boolean | null;
  professor: string | null;
  /** The student's section, e.g. "101"; "" clears it. */
  section: string | null;
  final_grade: number | null;
  target_grade: number | null;
  category_weights: Partial<Record<GradeCategory, number>> | null;
  start_date: string | null;
  end_date: string | null;
  no_final: boolean | null;
  transfer_credit: boolean | null;
  archived: boolean | null;
  links: CourseLink[] | null;
}


// Grade
/** One gradebook item of a course. */
export interface Grade {
  id: string;
  name: string;
  /** Null until marked; unmarked is not zero. */
  score: number | null;
  max_score: number;
  category: GradeCategory;
  weight: number;
  /** When the work is due or sat, YYYY-MM-DD; null for an undated item. */
  due_date: string | null;
  /** "HH:MM[:SS]" on the due date; null means no set time, not midnight. */
  due_time: string | null;
  /** Length of a calendar block; null for a task or an all-day block. */
  duration_minutes: number | null;
  /** Whether the date raises a task or a calendar block; ignored without a date. */
  schedule_as: GradeSchedule;
  /** Dropped: kept on the course but left out of every average. */
  excluded: boolean;
}

/** What a dated grade raises outside the gradebook. */
export enum GradeSchedule {
  /** A task that closes itself when the score lands. */
  TASK = "task",
  /** A calendar block and nothing else. */
  EVENT = "event",
}

/** Grade categories as the API spells them. */
export enum GradeCategory {
  ASSIGNMENT = "Assignment",
  LAB = "Lab",
  QUIZ = "Quiz",
  MIDTERM = "Midterm",
  PARTICIPATION = "Participation",
  PROJECT = "Project",
  OTHER = "Other",
  FINAL = "Final",
  /** Adds on top of the course average instead of forming part of it; see bonus.ts. */
  BONUS = "Bonus"
}

/** One unmarked item and what doing it is worth. */
export interface RemainingItem {
  grade_id: string;
  name: string;
  category: GradeCategory;
  max_score: number;
  due_date: string | null;
  /** Points of final course average this item still controls. */
  leverage: number;
  /** The student's own estimate, from the task this grade raised. */
  estimated_minutes: number | null;
  /** Leverage per hour; null without an estimate, never defaulted. */
  per_hour: number | null;
}

/** "Worth doing next": the cheapest unmarked work toward the target. */
export interface CheapestPath {
  target: number;
  current: number;
  /** The average if everything outstanding went perfectly. */
  best: number;
  /** Whether the target can still be reached at all. */
  reachable: boolean;
  /** The top three, ranked by points per hour, then by points. */
  items: RemainingItem[];
  /** How many items were outstanding before the cut to three. */
  remaining_count: number;
  /** Counted over the three shown, as is `unestimated_count`. */
  estimated_count: number;
  unestimated_count: number;
}

/** The best-to-worst range a course can still finish in. */
export interface GradeBand {
  /** Average with every outstanding item at full marks. */
  best: number;
  /** Average with every outstanding item at zero. */
  worst: number;
  /** The live average, between the two. */
  current: number;
  /** Nothing left to mark, so best and worst have met. */
  settled: boolean;
  outstanding_items: number;
  /** Weighted categories with nothing entered at all. */
  empty_categories: string[];
}

/** The score needed on the final to reach the target. */
export interface RequiredFinal {
  /** Percentage needed on the final; can fall outside 0-100. */
  needed: number;
  /** False when `needed` is above 100 or already below 0. */
  possible: boolean;
  /** Weighted categories with no marks yet, which the figure leaves out. */
  unfinished_categories: string[];
}

/** Request body replacing a course's category weights. */
export interface CategoryWeightsUpdate {
  category_weights: Partial<Record<GradeCategory, number>>;
}

/** Request body for adding a grade. */
export interface GradeCreate{
  name: string;
  /** Null adds the item unmarked. */
  score: number | null;
  max_score: number;
  category: GradeCategory;
  due_date: string | null;
  due_time: string | null;
  duration_minutes: number | null;
  schedule_as: GradeSchedule;
}

/** Patch body for a grade. */
export interface GradeUpdate{
  name: string | null;
  score: number | null;
  max_score: number | null;
  category: GradeCategory | null;
  due_date: string | null;
  due_time: string | null;
  duration_minutes: number | null;
  schedule_as: GradeSchedule | null;
  /** Dropped: kept on the course but left out of every average. */
  excluded: boolean | null;
}


// Error Handling
/** FastAPI's 422 body. */
export interface HTTPValidationError {
  detail: ValidationError[];
}

/** One entry of a FastAPI validation error. */
export interface ValidationError {
  loc: (string | number)[];
  msg: string;
  type: string;
  input: unknown;
  ctx?: Record<string, unknown>;
}


// User
/** A user's id, name and email. */
export interface User {
  id: string;
  name: string;
  email: string;
}

/** Request body for creating a user. */
export interface UserCreate {
  name: string;
  email: string;
}

/** A user with their courses. */
export interface UserDetail {
  id: string;
  name: string;
  email: string;
  courses: Course[];
}

/** Patch body for a user's name and email. */
export interface UserUpdate{
  name: string | null;
  email: string | null;
}


// Dashboard
/** One school year's average and course count. */
export interface YearSummary {
  school_year: number;
  /** Null when no course that year has anything recorded. */
  average: number | null;
  course_count: number;
}

/** Why a course is listed in Attention. */
export type AttentionKind = "missing_final" | "below_target" | "weight_problem" | "missing_section";

/** One Attention entry: a course and the problem to act on. */
export interface AttentionItem {
  kind: AttentionKind;
  course_id: string;
  course_code: string;
  message: string;
}

/* ===== Category blind spots ===== */

/** How far a category trails the student's overall average. */
export type BlindSpotSeverity = "mild" | "moderate" | "severe";

/** A category pooled across every graded course that trails the overall average. */
export interface CategoryBlindSpot {
  category: string;
  /** Pooled percentage over every marked item in this category. */
  average: number;
  /** The same pooling over every marked item in every category. */
  overall_average: number;
  /** `overall_average` minus `average`; always positive. */
  gap: number;
  severity: BlindSpotSeverity;
  course_count: number;
  item_count: number;
  /** Courses that fed the finding; there is no single course to link to. */
  course_codes: string[];
}

/** One term on the grade trend chart. */
export interface TermPoint {
  school_year: number;
  semester: string;
  label: string;
  /** Plain mean of that term's courses. */
  term_average: number;
  /** Credit-weighted cumulative up to that term; null until a course has a final. */
  cumulative_average: number | null;
}

/** The grades dashboard: averages, credits, Attention and the term history. */
export interface UserGradeDashboard {
  total_courses: number;
  /** Credit-weighted mean. */
  cumulative_average: number;
  /** Plain mean over the current term only. */
  semester_average: number;
  /** Null when the GPA scale is switched off in Settings. */
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

/** A course named on the dashboard, with the final score it needs. */
export interface CourseDashboardEntry {
  course_id: string;
  course_code: string;
  course_name: string;
  /** Null when nothing is marked; see `Course.average`. */
  average: number | null;
  needed_final_score: number | null;
  unfinished_categories: string[];
}

/** A course still waiting on its final, with the score it needs. */
export interface CourseNeedingFinalScore {
  course_id: string;
  course_code: string;
  course_name: string;
  /** Null when nothing is marked; see `Course.average`. */
  average: number | null;
  needed_final_score: number | null;
  unfinished_categories: string[];
}
/* ===== Grading schemes (Phase 1 item 4) ===== */

/** One category's part in a grading scheme. */
export interface SchemeComponent {
  category: GradeCategory;
  weight: number;
  /** How many of the category's lowest marks to leave out. */
  drop_lowest: number;
  /** A category whose higher average stands in for this one. */
  replace_with: GradeCategory | null;
}

/** An alternative grading scheme saved on a course. */
export interface GradingScheme {
  id: string;
  course_id: string;
  label: string;
  components: SchemeComponent[];
  created_at: string;
}

/** One category's line in a scheme's result. */
export interface SchemeLine {
  category: GradeCategory;
  weight: number;
  /** The category's average after the scheme's rules; null with nothing marked. */
  average: number | null;
  /** How many marks the drop rule left out. */
  dropped: number;
  replaced_by: GradeCategory | null;
}

/** A scheme applied to the course's marks. */
export interface SchemeResult {
  /** Null for the course's own weights. */
  id: string | null;
  label: string;
  average: number;
  lines: SchemeLine[];
  /** The scheme as written, rules included; what the editor starts from. */
  components: SchemeComponent[];
}

/** The course's own weights beside each saved scheme, with the best and the counted one. */
export interface SchemeComparison {
  current: SchemeResult;
  schemes: SchemeResult[];
  /** The scheme with the highest average when one beats the course's own; else null. */
  best_id: string | null;
  /** The scheme picked as the course's grade; null when its own weights are. */
  counting_id?: string | null;
}

/** A course as the school offers it: a shared catalogue row, the same for everyone. */
export interface CatalogueCourse {
  id: string;
  campus: "UBCV" | "UBCO" | string;
  subject: string;
  number: string;
  title: string | null;
  credits: number | null;
}

/**
 * A course's catalogue link: chosen by hand, matched by campus and code, none_chosen
 * when the student said there is none, or not_found when nothing matches yet.
 */
export interface CatalogueLink {
  how: "chosen" | "matched" | "none_chosen" | "not_found";
  course: CatalogueCourse | null;
}

/** The student's catalogue choice: automatic matching, none, or a picked course. */
export type CatalogueChoice =
  | { mode: "auto" }
  | { mode: "none" }
  | { mode: "chosen"; catalogue_course_id: string };

/** A prerequisite rule's outcome against the student's courses. */
export type RuleStatus = "met" | "on_track" | "not_met";
/** Which kind of requisite a rule is. */
export type PrerequisiteKindName = "prerequisite" | "corequisite";

/** A rule evaluated, as a tree of groups and single requirements. */
export interface RuleResult {
  status: RuleStatus;
  text: string;
  detail: string;
  parts: RuleResult[];
  /** "all" or "any" for a group; null for a single course or credit count. */
  group: "all" | "any" | null;
}

/** One version of a rule: typed or syllabus are the student's, reviewed or ubc-calendar shared. */
export interface PrerequisiteSide {
  source: "typed" | "syllabus" | "reviewed" | "ubc-calendar";
  rule: Record<string, unknown>;
  text: string;
  note: string | null;
  session: string | null;
  source_text: string | null;
  review: "pending" | "accepted" | "rejected" | null;
  result: RuleResult;
}

/** The student's and the catalogue's versions of one requisite kind, and which applies. */
export interface PrerequisiteKind {
  kind: PrerequisiteKindName;
  yours: PrerequisiteSide | null;
  shared: PrerequisiteSide | null;
  applies: "yours" | "shared" | null;
}

/** A course's catalogue link and requisite rules. */
export interface Prerequisites {
  course_id: string;
  link: CatalogueLink;
  kinds: PrerequisiteKind[];
}

/** Requisites for a course not yet added, looked up from the catalogue. */
export interface PrerequisitePreview {
  catalogue: CatalogueCourse | null;
  kinds: PrerequisiteKind[];
}

/** One 5-point band of a term's grade counts; 0 means below 50. */
export interface GradeCountBand {
  bucket: number;
  contributors: number;
}

/** One finished term's grade counts for a course, shown only above the floor. */
export interface TermDistribution {
  term_code: string;
  /** "Fall 2025". */
  term_label: string;
  contributors: number;
  median_bucket: number;
  bands: GradeCountBand[];
}

/** What other students' shared answers say about one of your courses. */
export interface ClassFigures {
  /** Null when the course's code isn't a course code, so nothing can be shown. */
  course_key: string | null;
  /** People a figure needs before it is shown. */
  floor: number;
  /** Newest term first; empty until one reaches the floor. */
  distributions: TermDistribution[];
  your_grade: number | null;
  your_bucket: number | null;
}
