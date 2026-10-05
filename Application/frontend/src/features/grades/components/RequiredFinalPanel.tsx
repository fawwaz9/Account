import { useEffect, useRef, useState } from "react";
import { fetchRequiredFinal } from "../api";
import { CourseDetail, GradeCategory, RequiredFinal } from "../types";

interface RequiredFinalPanelProps {
  readonly userId: string;
  readonly course: CourseDetail;
  /** The account's default target, used when the course has none of its own. */
  readonly defaultTarget: number;
  /** Bumped by the page whenever a grade changes, to refetch. */
  readonly nonce: number;
  /** Opens the calculator, for asking about a target other than the course's. */
  readonly onTryAnother: () => void;
}

/**
 * What the final must score to reach this course's target, without asking.
 *
 * The figure was always there, but behind a button and a form: you had to know
 * to look. Phase 1 item 2 puts it on the page, measured against the target the
 * course already has (or the account default, the same rule the Attention panel
 * uses), and keeps the calculator for "what if I aimed higher".
 *
 * Says nothing when it has nothing true to say: a course with no final, a
 * transfer credit, a past or future term, a final already marked, or an answer
 * that has not arrived. Never a placeholder while loading.
 */
export default function RequiredFinalPanel({
  userId,
  course,
  defaultTarget,
  nonce,
  onTryAnother,
}: RequiredFinalPanelProps) {
  const target = course.target_grade ?? defaultTarget;
  const applies = finalStillAhead(course);
  const [result, setResult] = useState<RequiredFinal | null>(null);
  // An older answer landing after a newer one would describe a course state
  // that no longer exists.
  const latestRequest = useRef(0);

  useEffect(() => {
    const ticket = ++latestRequest.current;
    let cancelled = false;
    setResult(null);
    if (!applies) return;

    fetchRequiredFinal(userId, course.id, target)
      .then((answer) => {
        if (!cancelled && ticket === latestRequest.current) setResult(answer);
      })
      .catch(() => {
        if (!cancelled && ticket === latestRequest.current) setResult(null);
      });

    return () => {
      cancelled = true;
    };
  }, [userId, course.id, target, applies, nonce]);

  if (!applies || !result) return null;

  return (
    <div className="requiredFinalPanel">
      <div className="gradeBandHead">
        <span className="gradeBandLabel">On the final</span>
        <span className="requiredFinalTarget">for {target}%</span>
      </div>

      <p className="requiredFinalPanelAnswer">{answerFor(result, target)}</p>

      {result.unfinished_categories.length > 0 && (
        <p className="gradeBandNote">
          Assumes nothing yet for {result.unfinished_categories.join(", ").toLowerCase()}
        </p>
      )}

      <button type="button" className="requiredFinalTryAnother" onClick={onTryAnother}>
        Try another target
      </button>
    </div>
  );
}

function answerFor(result: RequiredFinal, target: number): string {
  if (result.needed <= 0) return `${target}% is already secured. Any final keeps it.`;
  if (!result.possible) return `Out of reach: it would take ${result.needed}%.`;
  return `You need ${result.needed}%.`;
}

/** A current course that has a weighted final and no mark on it yet. */
export function finalStillAhead(course: CourseDetail): boolean {
  if (course.term_bucket !== "current") return false;
  if (course.no_final || course.transfer_credit) return false;
  if (!(course.category_weights[GradeCategory.FINAL] ?? 0)) return false;
  return !course.grades.some(
    (grade) => grade.category === GradeCategory.FINAL && grade.score !== null,
  );
}
