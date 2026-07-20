import { get, post, patch, del } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";
import { Course, CourseCreate, CourseUpdate,CourseDetail, Grade, GradeCreate, GradeUpdate } from "./types";

export async function fetchCourses(userId: string): Promise<Course[]> {
  return get<Course[]>(endpoints.grades.courses(userId));
}

export async function createCourse(userId: string, payload: CourseCreate) {
  return post<Course>(endpoints.grades.courses(userId), payload);
}

export async function fetchCourseDetail(userId: string, courseId: string) {
  return get<any>(endpoints.grades.courseDetail(userId, courseId));
}

export async function updateCourse(userId: string, courseId: string, payload: Partial<CourseUpdate>) {
  return patch<Course>(endpoints.grades.courseDetail(userId, courseId), payload);
}

export async function fetchCourseCategoryWeights(userId: string, courseId: string) {
  return get<any>(endpoints.grades.CategoryWeights(userId, courseId));
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