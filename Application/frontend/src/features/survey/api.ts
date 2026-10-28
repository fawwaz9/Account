import { get, post } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";

/** Answers to the disappointment question; dismissed closes it unanswered. */
export type SurveyAnswer = "very" | "somewhat" | "not" | "dismissed";

/** The survey question due for this user, if any. */
export function fetchPendingQuestion(userId: string) {
  return get<{ question: "disappointment" | null }>(endpoints.survey.pending(userId));
}

/** Record an answer to the disappointment question. */
export function answerQuestion(userId: string, answer: SurveyAnswer) {
  return post(endpoints.survey.responses(userId), { question: "disappointment", answer });
}
