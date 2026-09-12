import { isOverMax, marksOver } from "../bonus";

interface BonusNoteProps {
  readonly score: number | null;
  readonly maxScore: number;
}

/**
 * Confirms a score that has gone over its maximum, once it has.
 *
 * Deliberately silent otherwise. A permanent hint saying scores *may* exceed
 * their maximum would sit under every grade anyone ever entered to explain a
 * case that almost never applies; this says nothing until the unusual thing
 * actually happens, and then names it so it does not read as a slipped digit.
 */
export default function BonusNote({ score, maxScore }: BonusNoteProps) {
  const grade = { score, max_score: maxScore };
  if (!isOverMax(grade)) return null;

  const over = marksOver(grade);
  return (
    <p className="bonusNote" role="status">
      ★ bonus — {over} mark{over === 1 ? "" : "s"} over the maximum
    </p>
  );
}

/** The class for a score input, gold once the score has gone over its max. */
export function scoreInputClass(base: string, score: number | null, maxScore: number) {
  return isOverMax({ score, max_score: maxScore }) ? `${base} bonusInput` : base;
}
