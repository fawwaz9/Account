import { useEffect, useRef, useState } from "react";
import { fetchRequiredFinal } from "../api";
import { CourseDetail, GradeCategory, RequiredFinal } from "../types";

/** The course, the Settings default target, a refetch counter, and the calculator opener. */
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
 * The final-exam score this course needs for its own target, shown without asking.
 * Renders nothing unless the final is still ahead and the answer has arrived.
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

/** The panel's one-line answer: already secured, out of reach, or the score needed. */
function answerFor(result: RequiredFinal, target: number): string {
  if (result.needed <= 0) return `${target}% is already secured. Any final keeps it.`;
  if (!result.possible) return `Out of reach: it would take ${result.needed}%.`;
  return `You need ${result.needed}%.`;
}

/** True for a current course with a weighted final that has no mark yet. */
export function finalStillAhead(course: CourseDetail): boolean {
  if (course.term_bucket !== "current") return false;
  if (course.no_final || course.transfer_credit) return false;
  if (!(course.category_weights[GradeCategory.FINAL] ?? 0)) return false;
  return !course.grades.some(
    (grade) => grade.category === GradeCategory.FINAL && grade.score !== null,
  );
}
