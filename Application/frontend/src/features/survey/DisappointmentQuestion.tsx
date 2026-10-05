import { useEffect, useState } from "react";
import { answerQuestion, fetchPendingQuestion, SurveyAnswer } from "./api";

const CHOICES: { answer: SurveyAnswer; label: string }[] = [
  { answer: "very", label: "Very disappointed" },
  { answer: "somewhat", label: "Somewhat disappointed" },
  { answer: "not", label: "Not disappointed" },
];

/**
 * One question, asked once: how would you feel without Account?
 *
 * The Phase 1 exit gate counts "very disappointed" answers (account-vision.md
 * §11), and nothing else can read that. The server decides when to ask (after a
 * week of use) and never asks again after an answer -- "don't ask again"
 * included. Every press is acknowledged, and the card says thanks, then goes.
 */
export default function DisappointmentQuestion({ userId }: { readonly userId: string }) {
  const [asking, setAsking] = useState(false);
  const [sending, setSending] = useState<SurveyAnswer | null>(null);
  const [done, setDone] = useState<"answered" | "dismissed" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchPendingQuestion(userId)
      .then((pending) => {
        if (!cancelled) setAsking(pending.question === "disappointment");
      })
      .catch(() => {
        if (!cancelled) setAsking(false);
      });
    return () => { cancelled = true; };
  }, [userId]);

  async function answer(choice: SurveyAnswer) {
    setSending(choice);
    setError(null);
    try {
      await answerQuestion(userId, choice);
      setDone(choice === "dismissed" ? "dismissed" : "answered");
    } catch {
      setError("Couldn't save that. Try again in a moment.");
    } finally {
      setSending(null);
    }
  }

  if (done === "answered") {
    return (
      <section className="gradeSummary surveyCard">
        <p role="status">Thanks. That helps decide what to build next.</p>
      </section>
    );
  }
  if (done === "dismissed") {
    return (
      <section className="gradeSummary surveyCard">
        <p role="status">Okay, it won't ask again.</p>
      </section>
    );
  }
  if (!asking) return null;

  return (
    <section className="gradeSummary surveyCard" aria-label="A question">
      <p className="surveyQuestion">How would you feel if you could no longer use Account?</p>
      <div className="surveyChoices">
        {CHOICES.map(({ answer: choice, label }) => (
          <button
            key={choice}
            type="button"
            className="buttons"
            onClick={() => answer(choice)}
            disabled={sending !== null}
          >
            {sending === choice ? "Saving…" : label}
          </button>
        ))}
      </div>
      <button
        type="button"
        className="surveyDismiss"
        onClick={() => answer("dismissed")}
        disabled={sending !== null}
      >
        {sending === "dismissed" ? "Saving…" : "Don't ask again"}
      </button>
      {error && <p className="small-text error" role="alert">{error}</p>}
    </section>
  );
}
