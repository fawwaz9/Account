import { get, post, patch, put, del } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";
import { CheapestPath,
  CatalogueChoice,
  CatalogueCourse,
  CatalogueLink,
  PrerequisiteKindName,
  PrerequisitePreview,
  Prerequisites,
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

/** All of the student's courses. */
export async function fetchCourses(userId: string): Promise<Course[]> {
  return get<Course[]>(endpoints.grades.courses(userId));
}

/** Create a course. */
export async function createCourse(userId: string, payload: CourseCreate) {
  return post<Course>(endpoints.grades.courses(userId), payload);
}

/** One course with its grades and per-category figures. */
export async function fetchCourseDetail(userId: string, courseId: string) {
  return get<CourseDetail>(endpoints.grades.courseDetail(userId, courseId));
}

/** Patch a course with only the fields given. */
export async function updateCourse(userId: string, courseId: string, payload: Partial<CourseUpdate>) {
  return patch<Course>(endpoints.grades.courseDetail(userId, courseId), payload);
}

/** A course's category weights, keyed by category name. */
export async function fetchCourseCategoryWeights(userId: string, courseId: string) {
  return get<Partial<Record<string, number>>>(
    endpoints.grades.CategoryWeights(userId, courseId)
  );
}

/** Replace a course's category weights. */
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

/** Add a grade to a course. */
export async function createGrade(userId: string, courseId: string, payload: GradeCreate) {
  return post<Grade>(endpoints.grades.courseGrades(userId, courseId), payload);
}

/** Patch a grade with only the fields given. */
export async function updateGrade(userId: string, courseId: string, gradeId: string, payload: Partial<GradeUpdate>) {
  return patch<Grade>(endpoints.grades.gradeDetail(userId, courseId, gradeId), payload);
}

/** Delete a course; its grades, timetable and tasks go with it. */
export async function deleteCourse(userId: string, courseId: string) {
  return del<CourseDetail>(endpoints.grades.courseDetail(userId, courseId));
}

/** Delete one grade. */
export async function deleteGrade(userId: string, courseId: string, gradeId: string) {
  return del<Grade>(endpoints.grades.gradeDetail(userId, courseId, gradeId));
}
/** The grades dashboard; `targetGrade` overrides the target its needed-final figures use. */
export async function fetchDashboard(userId: string, targetGrade?: number) {
  const path = endpoints.grades.dashboard(userId);
  const query = targetGrade === undefined ? "" : `?target_grade=${targetGrade}`;
  return get<UserGradeDashboard>(`${path}${query}`);
}

/** Categories, pooled across courses, that trail the student's overall average. */
export async function fetchBlindSpots(userId: string) {
  return get<CategoryBlindSpot[]>(endpoints.grades.blindSpots(userId));
}

/** Set the score of an existing grade through the score endpoint. */
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

/** Search the student's courses on the server. */
export async function searchCourses(userId: string, query: string) {
  return get<Course[]>(
    `${endpoints.grades.courses(userId)}/search?query=${encodeURIComponent(query)}`
  );
}

/** The best-to-worst range a course can still finish in. */
export async function fetchGradeBand(userId: string, courseId: string) {
  return get<GradeBand>(endpoints.grades.gradeBand(userId, courseId));
}

/** The cheapest unmarked work toward a course's target. */
export async function fetchCheapestPath(userId: string, courseId: string) {
  return get<CheapestPath>(endpoints.grades.cheapestPath(userId, courseId));
}

/** The final-exam score a course needs to reach `targetGrade`. */
export async function fetchRequiredFinal(
  userId: string,
  courseId: string,
  targetGrade: number
) {
  return get<RequiredFinal>(
    `${endpoints.grades.requiredFinal(userId, courseId)}?target_grade=${targetGrade}`
  );
}

/** Add several grades in one transaction: all of them land or none do. */
export async function createGradesBulk(
  userId: string,
  courseId: string,
  payload: GradeCreate[]
) {
  return post<Grade[]>(endpoints.grades.bulkGrades(userId, courseId), payload);
}

/* ===== Grading schemes ===== */

/** The course's own weights beside each saved grading scheme. */
export async function fetchSchemes(userId: string, courseId: string) {
  return get<SchemeComparison>(endpoints.grades.schemes(userId, courseId));
}

/** Save a new alternative grading scheme on a course. */
export async function createScheme(
  userId: string, courseId: string, body: { label: string; components: SchemeComponent[] },
) {
  return post<GradingScheme>(endpoints.grades.schemes(userId, courseId), body);
}

/** Replace a scheme's label and components. */
export async function updateScheme(
  userId: string, courseId: string, schemeId: string, body: { label: string; components: SchemeComponent[] },
) {
  return put<GradingScheme>(endpoints.grades.scheme(userId, courseId, schemeId), body);
}

/** Delete an alternative scheme; callers confirm first. */
export async function deleteScheme(userId: string, courseId: string, schemeId: string) {
  return del<{ deleted: boolean }>(endpoints.grades.scheme(userId, courseId, schemeId));
}

/** Make a scheme the course's grade, or pass null to count its own weights again. */
export async function setCountingScheme(userId: string, courseId: string, schemeId: string | null) {
  return put<SchemeComparison>(endpoints.grades.countingScheme(userId, courseId), { scheme_id: schemeId });
}



/* ===== The shared catalogue (Phase 2 item 3) ===== */

/** Search the shared course catalogue. */
export async function searchCatalogue(userId: string, query: string) {
  return get<CatalogueCourse[]>(`${endpoints.grades.catalogue(userId)}?q=${encodeURIComponent(query)}`);
}

/** A course's link to the shared catalogue. */
export async function fetchCatalogueLink(userId: string, courseId: string) {
  return get<CatalogueLink>(endpoints.grades.courseCatalogue(userId, courseId));
}

/** Choose a course's catalogue link: automatic, none, or a picked course. */
export async function setCatalogueLink(userId: string, courseId: string, choice: CatalogueChoice) {
  return put<CatalogueLink>(endpoints.grades.courseCatalogue(userId, courseId), choice);
}


/* ===== Prerequisites (Phase 2 items 4 and 7) ===== */

/** A course's catalogue link and requisite rules, judged against the student's record. */
export async function fetchPrerequisites(userId: string, courseId: string) {
  return get<Prerequisites>(endpoints.grades.prerequisites(userId, courseId));
}

/** Save your own typed rule for one requisite kind; it applies to you at once. */
export async function saveOwnPrerequisite(
  userId: string, courseId: string, body: { kind: PrerequisiteKindName; text: string; note: string | null },
) {
  return put<Prerequisites>(endpoints.grades.prerequisites(userId, courseId), body);
}

/** Delete your own rule for one requisite kind. */
export async function deleteOwnPrerequisite(userId: string, courseId: string, kind: PrerequisiteKindName) {
  return del<Prerequisites>(`${endpoints.grades.prerequisites(userId, courseId)}?kind=${kind}`);
}

/** Parse a typed rule as it would be saved; rejects with the reason it can't be read. */
export async function checkPrerequisiteText(userId: string, text: string) {
  return post<{ rule: Record<string, unknown>; text: string }>(endpoints.grades.checkPrerequisite(userId), { text });
}

/** The shared requisites for a course not yet added, judged against your record. */
export async function previewPrerequisites(userId: string, code: string, year: number, semester: string) {
  const query = new URLSearchParams({ code, year: String(year), semester });
  return get<PrerequisitePreview>(`grades/${userId}/prerequisites/preview?${query}`);
}
