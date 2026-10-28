import type { Course } from "../types";
import { shortDate } from "../../../shared/utils/dateUtils";

/** The last projection before the final, set against the result; nothing until both exist. */
export default function ProjectionReview({ course }: { course: Course }) {
  const projected = course.projected_before_final;
  if (projected == null || !(course.final_grade > 0)) return null;

  const gap = Math.round((course.final_grade - projected) * 10) / 10;
  const verdict =
    gap === 0 ? "exactly as projected" : `${Math.abs(gap).toFixed(1)} ${gap > 0 ? "above" : "below"} it`;

  return (
    <p className="small-text projectionReview" role="note">
      {course.projected_on ? `On ${shortDate(course.projected_on)}, before the final, ` : "Before the final, "}
      we projected {projected.toFixed(1)}%. You got {course.final_grade}%, {verdict}.
    </p>
  );
}
