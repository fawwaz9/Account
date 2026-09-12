import { useEffect, useRef, useState } from "react";
import { fetchGradeBand } from "../api";
import { GradeBand as Band } from "../types";

interface GradeBandProps {
  readonly userId: string;
  readonly courseId: string;
  /** Bumped by the page whenever a grade changes, to refetch. */
  readonly nonce: number;
}

/**
 * Where this course can still finish.
 *
 * The running average cannot answer this on its own: 78% with everything marked
 * is a result, 78% with the final still to come is anywhere between a fail and
 * an A, and which one it is decides whether this is the course to spend the
 * weekend on.
 *
 * Hidden entirely once nothing is outstanding. A band that has closed is just
 * the average again, written three times.
 */
export default function GradeBand({ userId, courseId, nonce }: GradeBandProps) {
  const [band, setBand] = useState<Band | null>(null);
  // Grades can be edited faster than this round-trips, and an older answer
  // landing last would show a band for a course state that no longer exists.
  const latestRequest = useRef(0);

  useEffect(() => {
    const ticket = ++latestRequest.current;
    let cancelled = false;

    fetchGradeBand(userId, courseId)
      .then((result) => {
        if (!cancelled && ticket === latestRequest.current) setBand(result);
      })
      .catch(() => {
        if (!cancelled && ticket === latestRequest.current) setBand(null);
      });

    return () => {
      cancelled = true;
    };
  }, [userId, courseId, nonce]);

  if (!band || band.settled) return null;

  // The track is the full 0-100, so every figure is its own percentage along it
  // and a narrow band high up cannot be mistaken for a narrow band low down.
  const span = band.best - band.worst;

  return (
    <div className="gradeBand">
      <div className="gradeBandHead">
        <span className="gradeBandLabel">Can still finish</span>
        <span className="gradeBandRange">
          {band.worst} – {band.best}
        </span>
      </div>

      <div
        className="gradeBandTrack"
        role="img"
        aria-label={`Between ${band.worst} and ${band.best}, currently ${band.current}`}
      >
        <div
          className="gradeBandFill"
          style={{ left: `${band.worst}%`, width: `${Math.max(span, 0.5)}%` }}
        />
        <div className="gradeBandNow" style={{ left: `${band.current}%` }} />
      </div>

      <p className="gradeBandNote">
        {band.outstanding_items > 0 && (
          <>
            {band.outstanding_items} item{band.outstanding_items === 1 ? "" : "s"} left to mark
          </>
        )}
        {band.outstanding_items > 0 && band.empty_categories.length > 0 && " · "}
        {band.empty_categories.length > 0 && (
          <>nothing entered for {band.empty_categories.join(", ").toLowerCase()}</>
        )}
      </p>
    </div>
  );
}
