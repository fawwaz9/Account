import { useState } from "react";
import { Task } from "../types";
import { duration } from "../../../shared/utils/dateUtils";

/** Longest answer, in minutes; mirrors MAX_ESTIMATED_MINUTES in app/Tasks/schemas/task.py. */
const MAX_MINUTES = 2400;

/** The task just finished, and the answer and skip handlers. */
interface HowLongPromptProps {
  /** The task just ticked off, as the server returned it. */
  readonly task: Task;
  readonly onAnswer: (minutes: number) => Promise<void>;
  readonly onSkip: () => void;
}

/** Round minutes and keep them between 1 and `MAX_MINUTES`. */
function clamp(minutes: number): number {
  return Math.min(MAX_MINUTES, Math.max(1, Math.round(minutes)));
}

/**
 * "How long did it take?" card after an estimated task is ticked off, offering quick picks
 * (the timer's total first, when it ran) or a typed figure; skipping records nothing.
 */
export default function HowLongPrompt({ task, onAnswer, onSkip }: HowLongPromptProps) {
  const [typed, setTyped] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const estimate = task.estimated_minutes ?? 0;
  const timed = task.actual_minutes ?? null;
  const picks: { label: string; minutes: number }[] = [
    ...(timed ? [{ label: `Keep the timer's ${duration(timed)}`, minutes: timed }] : []),
    { label: `As estimated · ${duration(estimate)}`, minutes: estimate },
    { label: `Half · ${duration(clamp(estimate / 2))}`, minutes: clamp(estimate / 2) },
    { label: `1.5× · ${duration(clamp(estimate * 1.5))}`, minutes: clamp(estimate * 1.5) },
    { label: `2× · ${duration(clamp(estimate * 2))}`, minutes: clamp(estimate * 2) },
  ];
  const typedMinutes = Number(typed);
  const typedValid = typed.trim() !== "" && Number.isInteger(typedMinutes)
    && typedMinutes >= 1 && typedMinutes <= MAX_MINUTES;

  async function answer(minutes: number) {
    setSaving(true);
    setError(null);
    try {
      await onAnswer(minutes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save that.");
      setSaving(false);
    }
  }

  return (
    <section className="howLong" aria-label={`How long ${task.title} took`}>
      <p className="howLongQuestion">
        How long did <strong>{task.title}</strong> take? You estimated {duration(estimate)}.
        {timed ? ` The timer measured ${duration(timed)}.` : ""}
      </p>
      <div className="howLongPicks">
        {picks.map((pick) => (
          <button key={pick.label} type="button" className="calButton" disabled={saving}
                  onClick={() => void answer(pick.minutes)}>
            {pick.label}
          </button>
        ))}
      </div>
      <form className="howLongTyped" onSubmit={(event) => { event.preventDefault(); if (typedValid) void answer(typedMinutes); }}>
        <label>
          Minutes
          <input type="number" min={1} max={MAX_MINUTES} step={1} inputMode="numeric"
                 value={typed} onChange={(event) => setTyped(event.target.value)} disabled={saving} />
        </label>
        <button type="submit" className="calButton" disabled={saving || !typedValid}>Save</button>
        <button type="button" className="calButton howLongSkip" disabled={saving} onClick={onSkip}>
          Skip
        </button>
      </form>
      {error && <p className="small-text error" role="alert">{error}</p>}
    </section>
  );
}
