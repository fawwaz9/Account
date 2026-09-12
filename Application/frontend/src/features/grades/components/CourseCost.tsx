import { useEffect, useRef, useState } from "react";
import { fetchCourseCost } from "../../budget/api";
import { CourseCost as Cost } from "../../budget/types";
import { formatMoney } from "../../budget/money";

interface CourseCostProps {
  readonly userId: string;
  readonly courseId: string;
  /** Bumped by the page when something changes, to refetch. */
  readonly nonce: number;
}

/**
 * What this course cost.
 *
 * The tuition share is gross — its credits times the term's per-credit rate —
 * because a scholarship reduces what you paid, not what the course is worth. It
 * therefore will not tie out against the ledger, which records the net of one
 * payment for a whole term. That is the design, not a rounding problem.
 *
 * Hidden entirely when there is no cost at all, since an empty panel is noise.
 */
export default function CourseCost({ userId, courseId, nonce }: CourseCostProps) {
  const [cost, setCost] = useState<Cost | null>(null);
  const latestRequest = useRef(0);

  useEffect(() => {
    const ticket = ++latestRequest.current;
    let cancelled = false;

    fetchCourseCost(userId, courseId)
      .then((result) => {
        if (!cancelled && ticket === latestRequest.current) setCost(result);
      })
      .catch(() => {
        if (!cancelled && ticket === latestRequest.current) setCost(null);
      });

    return () => { cancelled = true; };
  }, [userId, courseId, nonce]);

  if (!cost || cost.total === 0) return null;

  return (
    <div className="courseCost">
      <div className="courseCostHead">
        <span className="courseCostLabel">What this cost</span>
        <strong className="courseCostTotal">{formatMoney(cost.total)}</strong>
      </div>

      <ul className="courseCostList">
        {cost.tuition_share > 0 && (
          <li>
            <span>
              Tuition · {cost.credits} cr × {formatMoney(cost.cost_per_credit)}
            </span>
            <span>{formatMoney(cost.tuition_share)}</span>
          </li>
        )}
        {cost.materials.map((line) => (
          <li key={line.label}>
            <span>{line.label}</span>
            <span>{formatMoney(line.amount)}</span>
          </li>
        ))}
      </ul>

      {cost.tuition_share > 0 && (
        <p className="courseCostNote">
          Tuition shown before any scholarship or deposit — those lower what you
          paid, not what the course is worth.
        </p>
      )}
    </div>
  );
}
