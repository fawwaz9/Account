import { isOverMax, marksOver } from "../bonus";

/** A grade's score and maximum. */
interface BonusNoteProps {
  readonly score: number | null;
  readonly maxScore: number;
}

/** A note shown only once a score passes its maximum, naming the marks over. */
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

/** A score input's class, plus the gold bonus class once the score passes its maximum. */
export function scoreInputClass(base: string, score: number | null, maxScore: number) {
  return isOverMax({ score, max_score: maxScore }) ? `${base} bonusInput` : base;
}
