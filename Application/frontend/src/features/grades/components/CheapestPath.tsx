import { useEffect, useRef, useState } from "react";
import { fetchCheapestPath } from "../api";
import { CheapestPath as Path, RemainingItem } from "../types";
import { duration } from "../../../shared/utils/dateUtils";

interface CheapestPathProps {
  readonly userId: string;
  readonly courseId: string;
  /** Bumped by the page whenever a grade changes, to refetch. */
  readonly nonce: number;
}

/** "+4.2 pts" — the share of the final average this item still controls. */
function points(value: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(1)} pts`;
}

function Row({ item }: { readonly item: RemainingItem }) {
  return (
    <li className="pathItem">
      <span className="pathItemName">
        {item.name}
        <span className="pathItemCategory">{item.category}</span>
      </span>
      <span className="pathItemFigures">
        {/* The rate leads because it is what the list is ordered on, and the
            raw points follow it, because a rate with no size attached cannot
            tell a big win from a cheap one -- 20 pts/h is an afternoon or a
            fortnight depending on the number beside it. */}
        {item.per_hour !== null && (
          <strong className="pathItemRate">{points(item.per_hour)}/h</strong>
        )}
        <span className="pathItemLeverage">{points(item.leverage)}</span>
        {item.estimated_minutes !== null && (
          <span className="pathItemEstimate">{duration(item.estimated_minutes)}</span>
        )}
      </span>
    </li>
  );
}

/**
 * Which remaining item is worth doing next.
 *
 * The average says where the course is; this says what to do about it. Each
 * item is scored by how much of the final average it still controls -- the
 * difference between finishing it perfectly and not at all.
 *
 * Three items, ranked by points per hour and then by points. The rate leads
 * because the question is what to spend the next hour on, and the server does
 * both the ranking and the cut -- a slice taken here would be a second rule
 * with nothing testing it.
 *
 * An item with no estimate has no rate and ranks below every item that has one,
 * so a single estimate anywhere in a course takes the top row whatever it is
 * worth. That is why the prompt to add estimates stays on screen rather than
 * being a hint that fades: it is the only thing that makes this ranking mean
 * anything.
 *
 * Hidden once nothing is outstanding, matching GradeBand: a course with nothing
 * left has no next thing to do.
 */
export default function CheapestPath({ userId, courseId, nonce }: CheapestPathProps) {
  const [path, setPath] = useState<Path | null>(null);
  // Grades can be edited faster than this round-trips, and an older answer
  // landing last would rank a course state that no longer exists.
  const latestRequest = useRef(0);

  useEffect(() => {
    const ticket = ++latestRequest.current;
    let cancelled = false;

    fetchCheapestPath(userId, courseId)
      .then((result) => {
        if (!cancelled && ticket === latestRequest.current) setPath(result);
      })
      .catch(() => {
        if (!cancelled && ticket === latestRequest.current) setPath(null);
      });

    return () => { cancelled = true; };
  }, [userId, courseId, nonce]);

  if (!path || path.items.length === 0) return null;

  return (
    <div className="cheapestPath">
      <div className="pathHead">
        <span className="pathLabel">Worth doing next</span>
        <span className="pathTarget">
          {path.current.toFixed(1)}% → target {path.target.toFixed(0)}%
        </span>
      </div>

      {/* Said before the list, not after it. A ranking read as a plan that
          reaches the target, when the arithmetic says it cannot, is worse than
          no ranking. */}
      {!path.reachable && (
        <p className="pathNote">
          Even with everything left at full marks this finishes at{" "}
          {path.best.toFixed(1)}%, so {path.target.toFixed(0)}% is out of reach.
          These are still the items that move it most.
        </p>
      )}

      <ul className="pathList">
        {path.items.map((item) => <Row key={item.grade_id} item={item} />)}
      </ul>

      {path.remaining_count > path.items.length && (
        <p className="pathNote">
          The top {path.items.length} of {path.remaining_count} still outstanding.
        </p>
      )}

      {/* Load bearing, not a nicety: without estimates this is ranked on points
          alone, and one estimate anywhere takes the top row on its own. */}
      {path.unestimated_count > 0 && (
        <p className="pathNote">
          {path.estimated_count === 0
            ? "None of these carry a time estimate, so they are ranked on points alone."
            : `${path.unestimated_count} of these carry no time estimate, so they rank below the ones that do.`}{" "}
          Add one in Tasks and it gets a rate here.
        </p>
      )}
    </div>
  );
}
