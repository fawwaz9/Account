import { Course, CourseDetail, Grade, GradeCategory } from "./types";

/**
 * Categories that add on top of a course average rather than compose it.
 * Must match ADDITIVE_CATEGORIES in the backend's Grades/utils/enums.py.
 */
export const ADDITIVE_CATEGORIES: readonly GradeCategory[] = [GradeCategory.BONUS];

/** True for a category that adds on top of the average (bonus). */
export function isAdditive(category: GradeCategory | string): boolean {
  return ADDITIVE_CATEGORIES.includes(category as GradeCategory);
}

/** True when a marked grade scored above its own maximum. */
export function isOverMax(grade: Pick<Grade, "score" | "max_score">): boolean {
  return grade.score !== null && grade.max_score > 0 && grade.score > grade.max_score;
}

/** Marks a grade went over its maximum by, to two decimals; 0 when it did not. */
export function marksOver(grade: Pick<Grade, "score" | "max_score">): number {
  if (!isOverMax(grade)) return 0;
  return Math.round(((grade.score as number) - grade.max_score) * 100) / 100;
}

/** True when a course has weighted bonus or any grade marked above its maximum. */
export function carriesBonus(course: CourseDetail | Course, grades?: Grade[]): boolean {
  const weighted = Object.entries(course.category_weights).some(
    ([category, weight]) => isAdditive(category) && (weight ?? 0) > 0
  );
  if (weighted) return true;

  const list = grades ?? (course as CourseDetail).grades ?? [];
  return list.some(isOverMax);
}

/** Sum of the non-bonus weights: what the course is marked out of. */
export function scoringWeight(
  weights: Partial<Record<GradeCategory, number>>
): number {
  return Object.entries(weights)
    .filter(([category]) => !isAdditive(category))
    .reduce((total, [, weight]) => total + (weight ?? 0), 0);
}

/** A copy of `categories` with bonus moved last, the rest in their given order. */
export function bonusLast(categories: GradeCategory[]): GradeCategory[] {
  return [...categories].sort((a, b) => Number(isAdditive(a)) - Number(isAdditive(b)));
}
