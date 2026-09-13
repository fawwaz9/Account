import { CategoryBlindSpot } from "../types";

interface BlindSpotsPanelProps {
  readonly spots: readonly CategoryBlindSpot[];
}

/**
 * A category worse than the student's own average, in more than one course.
 *
 * Pooled across every graded course, so this never links to a single course --
 * the point is that no one course explains it. Nothing shows here unless it
 * repeats in at least two of them; a category weak in one course is that
 * course's problem, not a pattern.
 */
export default function BlindSpotsPanel({ spots }: BlindSpotsPanelProps) {
  if (spots.length === 0) return null;

  return (
    <section className="blindSpotsPanel">
      <h3 className="attentionTitle">Category blind spots</h3>

      <ul className="blindSpotsList">
        {spots.map((spot) => (
          <li key={spot.category} className="blindSpotItem">
            <span className={`blindSpotTag blindSpotTag--${spot.severity}`}>
              {spot.category}
            </span>
            <span className="attentionBody">
              <span className="small-text">
                {spot.average}% here vs {spot.overall_average}% overall
              </span>
              <span className="small-text muted">
                Across {spot.course_count} courses, {spot.item_count} marked items
              </span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
