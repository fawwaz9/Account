import { del, get, post, put } from "../../services/apiClient";

/** A student's end-of-term answers about a course; mirrors app/Grades/schemas/term_review.py. */
export interface TermReviewAnswers {
  /** Hours a week the course took, 0-80; every answer is optional. */
  hours_per_week: number | null;
  /** 1-5. */
  difficulty: number | null;
  /** 1-5. */
  clarity: number | null;
  would_take_again: boolean | null;
  /** Opt-in to add this course's grade to the shared distribution. */
  contribute_grade: boolean;
}

/** A saved or skipped term review. */
export interface TermReview extends TermReviewAnswers {
  skipped: boolean;
  created_at: string;
  /** False once the answers have locked; the contribution stays changeable. */
  answers_editable: boolean;
}

/** A finished course in its review window, with the student's review if any. */
export interface ReviewCourse {
  course_id: string;
  code: string;
  name: string;
  /** e.g. "Fall 2025". */
  term_label: string;
  /** Whether there is a grade to contribute. */
  has_grade: boolean;
  /** False when the code doesn't read as a course or the term's dates are unknown. */
  can_contribute: boolean;
  review: TermReview | null;
}

/** Courses due or holding a term review. */
export interface TermReviews {
  courses: ReviewCourse[];
  /** Finished courses not yet answered or skipped. */
  pending: number;
}

/** Load the student's finished courses and their term reviews. */
export function fetchTermReviews(userId: string) {
  return get<TermReviews>(`grades/${userId}/term-reviews`);
}

/** Save one course's answers; a PUT, so sending it again is safe. */
export function saveTermReview(userId: string, courseId: string, answers: TermReviewAnswers) {
  return put<TermReview>(`grades/${userId}/term-reviews/${courseId}`, answers);
}

/** Mark one course's review as skipped. */
export function skipTermReview(userId: string, courseId: string) {
  return post<TermReview>(`grades/${userId}/term-reviews/${courseId}/skip`, {});
}

/** Delete a review and its answers; the next daily recount drops its contribution. */
export function removeTermReview(userId: string, courseId: string) {
  return del<{ deleted: boolean }>(`grades/${userId}/term-reviews/${courseId}`);
}
