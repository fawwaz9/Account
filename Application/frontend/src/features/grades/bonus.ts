import { Course, CourseDetail, Grade, GradeCategory } from "./types";

/**
 * Which categories add to a course rather than compose it.
 *
 * Mirrors ADDITIVE_CATEGORIES in the backend's Grades/utils/enums.py. The two
 * lists have to agree, but the frontend never decides the arithmetic -- it only
 * decides how to label what the server already computed.
 */
export const ADDITIVE_CATEGORIES: readonly GradeCategory[] = [GradeCategory.BONUS];

export function isAdditive(category: GradeCategory | string): boolean {
  return ADDITIVE_CATEGORIES.includes(category as GradeCategory);
}

/** A grade scoring above its own maximum: bonus marks on ordinary work. */
export function isOverMax(grade: Pick<Grade, "score" | "max_score">): boolean {
  return grade.score !== null && grade.max_score > 0 && grade.score > grade.max_score;
}

/** How many marks a grade went over by, for the label beside it. */
export function marksOver(grade: Pick<Grade, "score" | "max_score">): number {
  if (!isOverMax(grade)) return 0;
  return Math.round(((grade.score as number) - grade.max_score) * 100) / 100;
}

/**
 * Whether a course carries bonus at all, by either route.
 *
 * Two mechanisms reach the same place and the badge should not care which: an
 * explicit bonus category with weight on it, or an ordinary grade marked above
 * its own maximum. A course can carry both, which is also why this answers a
 * yes/no rather than trying to total them -- the backend owns that number.
 */
export function carriesBonus(course: CourseDetail | Course, grades?: Grade[]): boolean {
  const weighted = Object.entries(course.category_weights).some(
    ([category, weight]) => isAdditive(category) && (weight ?? 0) > 0
  );
  if (weighted) return true;

  const list = grades ?? (course as CourseDetail).grades ?? [];
  return list.some(isOverMax);
}

/**
 * The scoring weight of a course: what it is actually marked out of.
 *
 * Bonus excluded, so a course weighted 100% plus a 5% bonus still reads as 100.
 */
export function scoringWeight(
  weights: Partial<Record<GradeCategory, number>>
): number {
  return Object.entries(weights)
    .filter(([category]) => !isAdditive(category))
    .reduce((total, [, weight]) => total + (weight ?? 0), 0);
}

/**
 * Categories in the order they should be read, bonus last.
 *
 * Bonus is the footnote to a course, not one of its parts, so it belongs after
 * everything the course is marked out of regardless of where it lands in the
 * enum or in whatever order the API returned the weights.
 */
export function bonusLast(categories: GradeCategory[]): GradeCategory[] {
  return [...categories].sort((a, b) => Number(isAdditive(a)) - Number(isAdditive(b)));
}
