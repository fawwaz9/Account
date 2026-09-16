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
        {/* The rate leads where there is one, because it is the thing being
            ranked on -- and the raw points follow it, because a rate with no
            size attached cannot tell a big win from a cheap one. */}
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
 * One list, ranked by leverage, because that is the figure known for every
 * item. Ranking the estimated ones first was the obvious reading of "most per
 * hour" and running it over real courses showed why it is wrong: a course with
 * one estimated lab worth four points and an unestimated final worth forty-five
 * put the lab at the top. Carrying an estimate is not evidence of being worth
 * doing. Where a real comparison exists -- two or more estimates -- the best
 * rate is named instead.
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

  const bestValue = path.best_value_grade_id
    ? path.items.find((item) => item.grade_id === path.best_value_grade_id)
    : undefined;

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

      {/* Said rather than sorted on. The best rate is genuinely worth knowing
          and it is usually not the heaviest thing left, so it gets a line of
          its own instead of a place in the order it has not earned. */}
      {bestValue && (
        <p className="pathNote">
          Best value for the time: <strong>{bestValue.name}</strong>, at{" "}
          {points(bestValue.per_hour ?? 0)} an hour.
        </p>
      )}

      {path.unestimated_count > 0 && (
        <p className="pathNote">
          {path.estimated_count === 0
            ? "None of these carry a time estimate."
            : `${path.unestimated_count} of these carry no time estimate.`}{" "}
          Add one in Tasks and it gets a rate here.
        </p>
      )}
    </div>
  );
}
