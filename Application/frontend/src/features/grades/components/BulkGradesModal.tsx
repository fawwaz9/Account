import { useState } from "react";
import { createGradesBulk } from "../api";
import { GradeCategory, GradeCreate } from "../types";
import { getErrorMessage } from "./AddCourseModal";
import { useAuth } from "../../../app/auth/AuthContext";

interface BulkGradesModalProps {
  readonly open: boolean;
  readonly courseId: string;
  readonly onClose: () => void;
  readonly onGradesAdded: () => void;
}

interface Row {
  name: string;
  category: GradeCategory;
  score: string;
  max_score: string;
}

const emptyRow = (): Row => ({
  name: "",
  category: GradeCategory.ASSIGNMENT,
  score: "",
  max_score: "",
});

export default function BulkGradesModal({
  open,
  courseId,
  onClose,
  onGradesAdded,
}: BulkGradesModalProps) {
  const { user } = useAuth();
  const [rows, setRows] = useState<Row[]>([emptyRow(), emptyRow(), emptyRow()]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  function updateRow(index: number, patch: Partial<Row>) {
    setRows((current) =>
      current.map((row, i) => (i === index ? { ...row, ...patch } : row))
    );
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;

    // A blank row is just an unused slot, not an error.
    const filled = rows.filter((row) => row.name.trim() !== "" && row.max_score !== "");
    if (filled.length === 0) {
      setError("Fill in at least one row.");
      return;
    }

    const payload: GradeCreate[] = filled.map((row) => ({
      name: row.name.trim(),
      category: row.category,
      // Blank score means the work is not marked yet, not a zero.
      score: row.score === "" ? null : Number(row.score),
      max_score: Number(row.max_score),
    }));

    setSubmitting(true);
    setError(null);
    try {
      await createGradesBulk(user.id, courseId, payload);
      setRows([emptyRow(), emptyRow(), emptyRow()]);
      onGradesAdded();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="popup">
      <div className="addCoursePopup bulkPopup">
        <h2>Add Several Grades</h2>
        <p className="muted small-text">
          Leave a score blank for work that isn&apos;t marked yet. Blank rows are ignored.
        </p>

        <form onSubmit={handleSubmit}>
          <div className="bulkGrid">
            <span className="bulkHead">Name</span>
            <span className="bulkHead">Category</span>
            <span className="bulkHead">Score</span>
            <span className="bulkHead">Out of</span>
            <span />

            {rows.map((row, index) => (
              <BulkRow
                key={index}
                row={row}
                index={index}
                onChange={(patch) => updateRow(index, patch)}
                onRemove={() => setRows((current) => current.filter((_, i) => i !== index))}
                removable={rows.length > 1}
              />
            ))}
          </div>

          <button
            type="button"
            className="buttons bulkAddRow"
            onClick={() => setRows((current) => [...current, emptyRow()])}
          >
            + Add row
          </button>

          {error && <p className="error">{error}</p>}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700 !bg-slate-900 !text-slate-200"
              disabled={submitting}
            >
              Cancel
            </button>
            <button type="submit" className="rounded-lg !bg-gold !text-slate-950" disabled={submitting}>
              {submitting ? "Saving..." : "Save all"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

interface BulkRowProps {
  readonly row: Row;
  readonly index: number;
  readonly onChange: (patch: Partial<Row>) => void;
  readonly onRemove: () => void;
  readonly removable: boolean;
}

function BulkRow({ row, index, onChange, onRemove, removable }: BulkRowProps) {
  return (
    <>
      <input
        className="--input bulkInput"
        aria-label={`Name for row ${index + 1}`}
        value={row.name}
        onChange={(event) => onChange({ name: event.target.value })}
      />
      <select
        className="--select bulkInput"
        aria-label={`Category for row ${index + 1}`}
        value={row.category}
        onChange={(event) => onChange({ category: event.target.value as GradeCategory })}
      >
        {Object.values(GradeCategory).map((category) => (
          <option key={category} value={category}>
            {category}
          </option>
        ))}
      </select>
      <input
        className="--input bulkInput"
        type="number"
        min={0}
        aria-label={`Score for row ${index + 1}`}
        value={row.score}
        onChange={(event) => onChange({ score: event.target.value })}
      />
      <input
        className="--input bulkInput"
        type="number"
        min={0}
        aria-label={`Out of, for row ${index + 1}`}
        value={row.max_score}
        onChange={(event) => onChange({ max_score: event.target.value })}
      />
      <button
        type="button"
        className="bulkRemove"
        onClick={onRemove}
        disabled={!removable}
        aria-label={`Remove row ${index + 1}`}
      >
        ×
      </button>
    </>
  );
}
