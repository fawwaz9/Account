import { get, post } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";

export type SurveyAnswer = "very" | "somewhat" | "not" | "dismissed";

export function fetchPendingQuestion(userId: string) {
  return get<{ question: "disappointment" | null }>(endpoints.survey.pending(userId));
}

export function answerQuestion(userId: string, answer: SurveyAnswer) {
  return post(endpoints.survey.responses(userId), { question: "disappointment", answer });
}
