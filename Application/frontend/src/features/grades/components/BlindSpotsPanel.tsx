import { CategoryBlindSpot } from "../types";

/** The blind spots to list. */
interface BlindSpotsPanelProps {
  readonly spots: readonly CategoryBlindSpot[];
}

/** Categories trailing the student's overall average across courses; renders nothing when none. */
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
