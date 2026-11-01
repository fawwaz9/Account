import { useEffect, useState } from "react";
import { fetchDropPreview } from "../api";
import { DropFigures, DropPreview } from "../types";
import { getErrorMessage } from "./AddCourseModal";
import Modal from "../../../shared/components/Modal";

/** The course and the close handler. */
interface DropPreviewModalProps {
  readonly userId: string;
  readonly courseId: string;
  readonly courseCode: string;
  readonly onClose: () => void;
}

/** The full-time line to start from (D9): an editable default, not a fact about you. */
const DEFAULT_FULL_TIME = 9;

/** The rows the table shows, each a label and how to read it from one side. */
const ROWS: { label: string; read: (f: DropFigures) => number | null; unit: string }[] = [
  { label: "Credits this term", read: (f) => f.term_credits, unit: "" },
  { label: "Semester average", read: (f) => f.semester_average, unit: "%" },
  { label: "Cumulative average", read: (f) => f.cumulative_average || null, unit: "%" },
  { label: "CGPA", read: (f) => f.cgpa, unit: "" },
  { label: "Cumulative, including this term", read: (f) => f.cumulative_average_including_term, unit: "%" },
  { label: "CGPA, including this term", read: (f) => f.cgpa_including_term, unit: "" },
];

/** A figure with its unit, or a dash for none. */
function show(value: number | null, unit: string): string {
  return value === null ? "–" : `${value}${unit}`;
}

/**
 * The course-drop simulator (Phase 4 item 11, §13.6): before and after for dropping one
 * of this term's courses, the full-time check and a refund ceiling. Information with
 * disclaimers, never advice; nothing is changed.
 */
export default function DropPreviewModal({ userId, courseId, courseCode, onClose }: DropPreviewModalProps) {
  const [fullTime, setFullTime] = useState(DEFAULT_FULL_TIME);
  const [preview, setPreview] = useState<DropPreview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!(fullTime >= 1 && fullTime <= 30)) return;
    let cancelled = false;
    fetchDropPreview(userId, courseId, fullTime)
      .then((answer) => { if (!cancelled) { setPreview(answer); setError(null); } })
      .catch((err) => { if (!cancelled) setError(getErrorMessage(err)); });
    return () => { cancelled = true; };
  }, [userId, courseId, fullTime]);

  // Only rows with a figure on either side; a CGPA row is noise with the scale off.
  const rows = preview ? ROWS.filter((row) => row.read(preview.before) !== null || row.read(preview.after) !== null) : [];
  const [first, ...rest] = preview?.warnings ?? [];

  return (
    <Modal title={`If you drop ${courseCode}`} onClose={onClose} panelClassName="dropPanel">
      <p className="muted small-text">Nothing changes until you actually drop it.</p>

      {error && <p className="error">{error}</p>}

      {preview && (
        <>
          <table className="dropTable">
            <thead>
              <tr><th scope="col"></th><th scope="col">Now</th><th scope="col">Without it</th></tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.label}>
                  <th scope="row">{row.label}</th>
                  <td>{show(row.read(preview.before), row.unit)}</td>
                  <td>{show(row.read(preview.after), row.unit)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <label className="dropThreshold">
            Full-time from
            <input
              className="dropThresholdInput" type="number" min={1} max={30} step={0.5} value={fullTime}
              onChange={(event) => setFullTime(Number(event.target.value))}
              aria-label="Credits a term that count as full-time"
            />
            credits a term
          </label>

          {first && (
            <p className={preview.below_full_time ? "dropWarning dropWarningSerious" : "dropWarning"} role="note">
              {first}
            </p>
          )}
          <ul className="dropNotes small-text">
            {rest.map((line) => <li key={line}>{line}</li>)}
            {preview.disclaimers.map((line) => <li key={line} className="muted">{line}</li>)}
          </ul>
        </>
      )}

      <div className="flex justify-end gap-3 pt-4">
        <button type="button" onClick={onClose}
          className="rounded-lg border border-slate-700 !bg-slate-900 !text-slate-200">
          Close
        </button>
      </div>
    </Modal>
  );
}
