import { useEffect, useState } from "react";
import { fetchShiftConflicts } from "../api";
import { ShiftConflict, ShiftConflicts } from "../types";
import { shortDate } from "../../../shared/utils/dateUtils";

/** "08:30" from "08:30:00"; null when the time is not set. */
export function clock(value: string | null) {
  return value ? value.slice(0, 5) : null;
}

/** One conflict in words: the job and shift, and whether it runs into or crowds the exam. */
export function conflictWords(conflict: ShiftConflict) {
  const exam = `${conflict.course_code ? `${conflict.course_code} ` : ""}${conflict.exam_title}`;
  const examWhen = `${shortDate(conflict.exam_on)}${clock(conflict.exam_start) ? ` at ${clock(conflict.exam_start)}` : ", time not set"}`;
  const shiftWhen = `${shortDate(conflict.shift_on)}${clock(conflict.shift_start) ? ` ${clock(conflict.shift_start)}–${clock(conflict.shift_end) ?? "?"}` : ""}`;
  const job = conflict.job_name ?? "A shift";
  return conflict.kind === "overlap"
    ? `${job}, ${shiftWhen}, runs into ${exam} (${examWhen}).`
    : `${job}, ${shiftWhen}, ends ${conflict.hours_between}h before ${exam} (${examWhen}).`;
}

/** Props for the shift-exam conflicts panel. */
interface Props {
  readonly userId: string;
  readonly nonce: number;
}

/** Shifts that run into, or crowd, an upcoming exam; nothing when there are none or it fails. */
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
