import { del, get, post, put } from "../../services/apiClient";

/** Mirrors app/Grades/schemas/term_review.py (Phase 2 item 13, D25). */
export interface TermReviewAnswers {
  hours_per_week: number | null;
  difficulty: number | null;
  clarity: number | null;
  would_take_again: boolean | null;
  contribute_grade: boolean;
}

export interface TermReview extends TermReviewAnswers {
  skipped: boolean;
  created_at: string;
  /** False once the answers have locked; the contribution stays changeable. */
  answers_editable: boolean;
}

export interface ReviewCourse {
  course_id: string;
  code: string;
  name: string;
  term_label: string;
  has_grade: boolean;
  can_contribute: boolean;
  review: TermReview | null;
}

export interface TermReviews {
  courses: ReviewCourse[];
  pending: number;
}

export function fetchTermReviews(userId: string) {
  return get<TermReviews>(`grades/${userId}/term-reviews`);
}

export function saveTermReview(userId: string, courseId: string, answers: TermReviewAnswers) {
  return put<TermReview>(`grades/${userId}/term-reviews/${courseId}`, answers);
}

export function skipTermReview(userId: string, courseId: string) {
  return post<TermReview>(`grades/${userId}/term-reviews/${courseId}/skip`, {});
}

/** Your answers and your contribution go; the next daily recount drops it. */
export function removeTermReview(userId: string, courseId: string) {
  return del<{ deleted: boolean }>(`grades/${userId}/term-reviews/${courseId}`);
}
