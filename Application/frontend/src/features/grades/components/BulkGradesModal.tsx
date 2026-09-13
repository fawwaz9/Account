import { useState } from "react";
import { createGradesBulk } from "../api";
import { GradeCategory, GradeCreate, GradeSchedule } from "../types";
import { getErrorMessage } from "./AddCourseModal";
import { useAuth } from "../../../app/auth/AuthContext";
import Modal from "../../../shared/components/Modal";

interface BulkGradesModalProps {
  readonly open: boolean;
  readonly courseId: string;
  readonly onClose: () => void;
  readonly onGradesAdded: () => void;
}

interface Row {
  /**
   * Identity that survives its position. Keying these by array index meant that
   * removing row 1 while editing row 3 handed row 3's focused input to row 4's
   * data -- React reuses the DOM node for the key, and the keystroke in flight
   * landed on the wrong row.
   */
  id: string;
  name: string;
  category: GradeCategory;
  score: string;
  max_score: string;
}

let nextRowId = 0;

const emptyRow = (): Row => ({
  id: `row-${nextRowId++}`,
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
      // Bulk entry is for catching a course up on marks already awarded, so
      // there is no deadline, and with no date the choice below decides nothing.
      // Both are set per grade afterwards.
      due_date: null,
      schedule_as: GradeSchedule.TASK,
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
    <Modal title="Add Several Grades" onClose={onClose} panelClassName="bulkPopup">
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
              key={row.id}
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
    </Modal>
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
        step="any"
        min={0}
        aria-label={`Score for row ${index + 1}`}
        value={row.score}
        onChange={(event) => onChange({ score: event.target.value })}
      />
      <input
        className="--input bulkInput"
        type="number"
        step="any"
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
