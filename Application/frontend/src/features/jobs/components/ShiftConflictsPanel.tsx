import { useEffect, useState } from "react";
import { fetchShiftConflicts } from "../api";
import { ShiftConflict, ShiftConflicts } from "../types";
import { shortDate } from "../../../shared/utils/dateUtils";

/** "08:30" from "08:30:00"; null is "time not set". */
export function clock(value: string | null) {
  return value ? value.slice(0, 5) : null;
}

export function conflictWords(conflict: ShiftConflict) {
  const exam = `${conflict.course_code ? `${conflict.course_code} ` : ""}${conflict.exam_title}`;
  const examWhen = `${shortDate(conflict.exam_on)}${clock(conflict.exam_start) ? ` at ${clock(conflict.exam_start)}` : ", time not set"}`;
  const shiftWhen = `${shortDate(conflict.shift_on)}${clock(conflict.shift_start) ? ` ${clock(conflict.shift_start)}–${clock(conflict.shift_end) ?? "?"}` : ""}`;
  const job = conflict.job_name ?? "A shift";
  return conflict.kind === "overlap"
    ? `${job}, ${shiftWhen}, runs into ${exam} (${examWhen}).`
    : `${job}, ${shiftWhen}, ends ${conflict.hours_between}h before ${exam} (${examWhen}).`;
}

interface Props {
  readonly userId: string;
  readonly nonce: number;
}

/**
 * Shifts that run into, or crowd, an exam in the next two months (Phase 2
 * item 14). Says nothing when there are none, or when the read fails: an
 * empty "no conflicts" box would be a line on the page with nothing to say.
 */
export default function ShiftConflictsPanel({ userId, nonce }: Props) {
  const [data, setData] = useState<ShiftConflicts | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchShiftConflicts(userId)
      .then((found) => { if (!cancelled) setData(found); })
      .catch(() => { if (!cancelled) setData(null); });
    return () => { cancelled = true; };
  }, [userId, nonce]);

  if (!data || data.conflicts.length === 0) return null;
  return (
    <section className="shiftConflicts" aria-label="Shifts near exams">
      <h2>Shifts near exams</h2>
      <ul>
        {data.conflicts.map((conflict) => (
          <li key={`${conflict.shift_event_id}-${conflict.shift_on}-${conflict.exam_event_id}`}
              className={`shiftConflict shiftConflict--${conflict.kind}`}>
            {conflictWords(conflict)}
          </li>
        ))}
      </ul>
      <p className="small-text muted">
        Flagged when a shift ends less than {data.buffer_hours}h before an exam. Change that in Settings,
        under Calendar.
      </p>
    </section>
  );
}
