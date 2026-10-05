import { get, post, patch, put, del } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";
import { CheapestPath,
  GradingScheme,
  SchemeComparison,
  SchemeComponent,
  GradeBand,
  CategoryBlindSpot,
  CategoryWeightsUpdate,
  Course,
  CourseCreate,
  CourseDetail,
  CourseUpdate,
  Grade,
  GradeCreate,
  GradeUpdate,
  RequiredFinal,
  UserGradeDashboard,
} from "./types";

export async function fetchCourses(userId: string): Promise<Course[]> {
  return get<Course[]>(endpoints.grades.courses(userId));
}

export async function createCourse(userId: string, payload: CourseCreate) {
  return post<Course>(endpoints.grades.courses(userId), payload);
}

export async function fetchCourseDetail(userId: string, courseId: string) {
  return get<CourseDetail>(endpoints.grades.courseDetail(userId, courseId));
}

export async function updateCourse(userId: string, courseId: string, payload: Partial<CourseUpdate>) {
  return patch<Course>(endpoints.grades.courseDetail(userId, courseId), payload);
}

export async function fetchCourseCategoryWeights(userId: string, courseId: string) {
  return get<Partial<Record<string, number>>>(
    endpoints.grades.CategoryWeights(userId, courseId)
  );
}

export async function updateCategoryWeights(
  userId: string,
  courseId: string,
  payload: CategoryWeightsUpdate
) {
  return patch<Partial<Record<string, number>>>(
    endpoints.grades.CategoryWeights(userId, courseId),
    payload
  );
}

export async function createGrade(userId: string, courseId: string, payload: GradeCreate) {
  return post<Grade>(endpoints.grades.courseGrades(userId, courseId), payload);
}

export async function updateGrade(userId: string, courseId: string, gradeId: string, payload: Partial<GradeUpdate>) {
  return patch<Grade>(endpoints.grades.gradeDetail(userId, courseId, gradeId), payload);
}

export async function deleteCourse(userId: string, courseId: string) {
  return del<CourseDetail>(endpoints.grades.courseDetail(userId, courseId));
}

export async function deleteGrade(userId: string, courseId: string, gradeId: string) {
  return del<Grade>(endpoints.grades.gradeDetail(userId, courseId, gradeId));
}
/**
 * Cross-course rollup: best and weakest course, overall and credit-weighted
 * averages, and what is still needed on each final.
 */
export async function fetchDashboard(userId: string, targetGrade?: number) {
  const path = endpoints.grades.dashboard(userId);
  const query = targetGrade === undefined ? "" : `?target_grade=${targetGrade}`;
  return get<UserGradeDashboard>(`${path}${query}`);
}

/** A category consistently worse than the student's own average, in more than one course. */
export async function fetchBlindSpots(userId: string) {
  return get<CategoryBlindSpot[]>(endpoints.grades.blindSpots(userId));
}

/** Record a score against an existing (previously ungraded) assignment. */
export async function recordGrade(
  userId: string,
  courseId: string,
  gradeId: string,
  score: number
) {
  return patch<Grade>(
    `${endpoints.grades.gradeDetail(userId, courseId, gradeId)}/score?score=${score}`,
    null
  );
}

/** Server-side search, for when the local list is no longer the whole set. */
export async function searchCourses(userId: string, query: string) {
  return get<Course[]>(
    `${endpoints.grades.courses(userId)}/search?query=${encodeURIComponent(query)}`
  );
}

/** What score is needed on the final to finish the course at `targetGrade`. */
export async function fetchGradeBand(userId: string, courseId: string) {
  return get<GradeBand>(endpoints.grades.gradeBand(userId, courseId));
}

export async function fetchCheapestPath(userId: string, courseId: string) {
  return get<CheapestPath>(endpoints.grades.cheapestPath(userId, courseId));
}

export async function fetchRequiredFinal(
  userId: string,
  courseId: string,
  targetGrade: number
) {
  return get<RequiredFinal>(
    `${endpoints.grades.requiredFinal(userId, courseId)}?target_grade=${targetGrade}`
  );
}

/**
 * Add several grades at once. The server commits them in one transaction, so
 * either every row lands or none does -- entering a course one modal at a time
 * meant a dozen requests that could each fail halfway.
 */
export async function createGradesBulk(
  userId: string,
  courseId: string,
  payload: GradeCreate[]
) {
  return post<Grade[]>(endpoints.grades.bulkGrades(userId, courseId), payload);
}

/* ===== Grading schemes ===== */

export async function fetchSchemes(userId: string, courseId: string) {
  return get<SchemeComparison>(endpoints.grades.schemes(userId, courseId));
}

export async function createScheme(
  userId: string, courseId: string, body: { label: string; components: SchemeComponent[] },
) {
  return post<GradingScheme>(endpoints.grades.schemes(userId, courseId), body);
}

export async function updateScheme(
  userId: string, courseId: string, schemeId: string, body: { label: string; components: SchemeComponent[] },
) {
  return put<GradingScheme>(endpoints.grades.scheme(userId, courseId, schemeId), body);
}

/** Remove an alternative scheme. Permanent, so it is confirmed first. */
export async function deleteScheme(userId: string, courseId: string, schemeId: string) {
  return del<{ deleted: boolean }>(endpoints.grades.scheme(userId, courseId, schemeId));
}
