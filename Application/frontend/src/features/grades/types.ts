// Course
export interface Course {
  id: string;
  code: string;
  name: string;
  year: number;
  semester: Semester;
  credits: number;
  required: boolean;
  professor: string;
  final_grade: number;
  category_weights: Partial<Record<GradeCategory, number>>;
  average: number;
  start_date: string | null;
  end_date: string | null;
}

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
  professor: string;
  final_grade: number;
  category_weights: Partial<Record<GradeCategory, number>>;
  // ISO yyyy-mm-dd, or null for a course with no set term dates
  start_date: string | null;
  end_date: string | null;
}

export interface CourseDetail {
  id: string;
  code: string;
  name: string;
  year: number;
  semester: Semester;
  credits: number;
  required: boolean;
  professor: string;
  final_grade: number;
  category_weights: Partial<Record<GradeCategory, number>>;
  average: number;
  grades: Grade[];
  start_date: string | null;
  end_date: string | null;
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
  category_weights: Partial<Record<GradeCategory, number>> | null;
  start_date: string | null;
  end_date: string | null;
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
}

export enum GradeCategory {
  ASSIGNMENT = "Assignment",
  LAB = "Lab",
  QUIZ = "Quiz",
  MIDTERM = "Midterm",
  PARTICIPATION = "Participation",
  PROJECT = "Project",
  OTHER = "Other",
  FINAL = "Final"
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
}

export interface GradeUpdate{
  name: string | null;
  score: number | null;
  max_score: number | null;
  category: GradeCategory | null;
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
export interface UserGradeDashboard {
  total_courses: number;
  /** Plain mean across courses */
  overall_average: number;
  /** Credit-weighted mean */
  cumulative_average: number;
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