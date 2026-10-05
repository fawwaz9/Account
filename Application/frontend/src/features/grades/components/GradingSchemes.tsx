import { useEffect, useRef, useState } from "react";
import Modal from "../../../shared/components/Modal";
import DeleteConfirmModal from "./DeleteConfirmModal";
import { createScheme, deleteScheme, fetchSchemes, updateScheme } from "../api";
import {
  CourseDetail,
  GradeCategory,
  SchemeComparison,
  SchemeComponent,
  SchemeResult,
} from "../types";

interface GradingSchemesProps {
  readonly userId: string;
  readonly course: CourseDetail;
  /** Bumped by the page whenever a grade changes, to refetch. */
  readonly nonce: number;
}

const CATEGORIES = Object.values(GradeCategory);

/**
 * Other ways this course can be graded, side by side -- Phase 1 item 4.
 *
 * The course's own weights stay its grade; each scheme here is another reading
 * of the same marks. "87.2% under Scheme B" means nothing without the working
 * (account-vision.md §7), so every figure opens into its categories: the
 * average after the scheme's rules, what was dropped, what replaced what.
 */
export default function GradingSchemes({ userId, course, nonce }: GradingSchemesProps) {
  const [comparison, setComparison] = useState<SchemeComparison | null>(null);
  const [editing, setEditing] = useState<SchemeResult | "new" | null>(null);
  const [removing, setRemoving] = useState<SchemeResult | null>(null);
  const [removingBusy, setRemovingBusy] = useState(false);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const latest = useRef(0);

  useEffect(() => {
    const ticket = ++latest.current;
    fetchSchemes(userId, course.id)
      .then((result) => { if (ticket === latest.current) setComparison(result); })
      .catch(() => { if (ticket === latest.current) setComparison(null); });
  }, [userId, course.id, nonce, refresh]);

  async function confirmRemove() {
    if (!removing?.id) return;
    setRemovingBusy(true);
    setRemoveError(null);
    try {
      await deleteScheme(userId, course.id, removing.id);
      setRemoving(null);
      setRefresh((n) => n + 1);
    } catch {
      setRemoveError("Couldn't remove that scheme.");
    } finally {
      setRemovingBusy(false);
    }
  }

  if (!comparison) return null;

  return (
    <section className="gradingSchemes" aria-label="Grading schemes">
      {comparison.schemes.length > 0 && (
        <>
          <h2>Other grading schemes</h2>
          <ul>
            <SchemeRow result={comparison.current} />
            {comparison.schemes.map((result) => (
              <SchemeRow
                key={result.id}
                result={result}
                best={result.id === comparison.best_id}
                onEdit={() => setEditing(result)}
                onRemove={() => { setRemoveError(null); setRemoving(result); }}
              />
            ))}
          </ul>
        </>
      )}
      <button type="button" className="requiredFinalTryAnother" onClick={() => setEditing("new")}>
        Add another grading scheme
      </button>

      {editing && (
        <SchemeEditor
          userId={userId}
          course={course}
          editing={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); setRefresh((n) => n + 1); }}
        />
      )}

      <DeleteConfirmModal
        open={removing !== null}
        title="Remove this scheme?"
        message={removing ? `"${removing.label}" will be removed. Your marks and the course's own weights are not touched.` : ""}
        onConfirm={confirmRemove}
        onCancel={() => setRemoving(null)}
        submitting={removingBusy}
        error={removeError}
        confirmLabel="Remove"
      />
    </section>
  );
}

function SchemeRow({
  result, best = false, onEdit, onRemove,
}: {
  readonly result: SchemeResult;
  readonly best?: boolean;
  readonly onEdit?: () => void;
  readonly onRemove?: () => void;
}) {
  return (
    <li className={best ? "schemeRow schemeBest" : "schemeRow"}>
      <details>
        <summary>
          <span>{result.label}</span>
          <strong>{result.average}%</strong>
          {best && <span className="small-text schemeBadge">higher</span>}
        </summary>
        <table className="schemeLines">
          <tbody>
            {result.lines.map((line) => (
              <tr key={line.category}>
                <th scope="row">{line.category}</th>
                <td>{line.weight}%</td>
                <td>{line.average === null ? "nothing marked" : `${line.average}%`}</td>
                <td className="small-text muted">
                  {[
                    line.dropped ? `lowest ${line.dropped} dropped` : "",
                    line.replaced_by ? `${line.replaced_by} counted instead` : "",
                  ].filter(Boolean).join(" · ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
      {onEdit && (
        <span className="schemeActions">
          <button type="button" className="calButton" onClick={onEdit}>Edit</button>
          <button type="button" className="calButton" onClick={onRemove}>Remove</button>
        </span>
      )}
    </li>
  );
}

function SchemeEditor({
  userId, course, editing, onClose, onSaved,
}: {
  readonly userId: string;
  readonly course: CourseDetail;
  readonly editing: SchemeResult | null;
  readonly onClose: () => void;
  readonly onSaved: () => void;
}) {
  const [label, setLabel] = useState(editing?.label ?? "Scheme B");
  const [rows, setRows] = useState<SchemeComponent[]>(() => {
    // An edited scheme starts from its rules as written -- never from what the
    // rules have done to the marks so far, which can be less ("drop 2" with
    // one mark yet).
    if (editing) return editing.components.map((component) => ({ ...component }));
    // A new one starts from the course's own weights: most alternative
    // schemes are the same categories with different numbers.
    return Object.entries(course.category_weights)
      .filter(([, weight]) => (weight ?? 0) > 0)
      .map(([category, weight]) => ({
        category: category as GradeCategory, weight: weight ?? 0, drop_lowest: 0, replace_with: null,
      }));
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const used = new Set(rows.map((row) => row.category));
  const unused = CATEGORIES.filter((category) => !used.has(category));

  function edit(index: number, change: Partial<SchemeComponent>) {
    setRows(rows.map((row, at) => (at === index ? { ...row, ...change } : row)));
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const body = { label: label.trim(), components: rows };
      if (editing?.id) await updateScheme(userId, course.id, editing.id, body);
      else await createScheme(userId, course.id, body);
      onSaved();
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Couldn't save that scheme.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title={editing ? "Edit grading scheme" : "Add a grading scheme"} onClose={onClose}>
      <label className="importPick">
        <span className="small-text muted">Name</span>
        <input className="--input" value={label} onChange={(e) => setLabel(e.target.value)} aria-label="Scheme name" />
      </label>
      <table className="schemeEditor">
        <thead>
          <tr>
            <th scope="col">Category</th>
            <th scope="col">Weight %</th>
            <th scope="col">Drop lowest</th>
            <th scope="col">Replaced by, if higher</th>
            <th scope="col" aria-label="Remove" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.category}>
              <th scope="row">{row.category}</th>
              <td>
                <input className="--input syllabusNumber" type="number" min={0} max={100} step="0.5"
                  value={row.weight} aria-label={`${row.category} weight`}
                  onChange={(e) => edit(index, { weight: Number(e.target.value) })} />
              </td>
              <td>
                <input className="--input syllabusNumber" type="number" min={0} max={20}
                  value={row.drop_lowest} aria-label={`${row.category} drop lowest`}
                  onChange={(e) => edit(index, { drop_lowest: Math.max(0, Number(e.target.value) || 0) })} />
              </td>
              <td>
                <select className="--input" value={row.replace_with ?? ""} aria-label={`${row.category} replaced by`}
                  onChange={(e) => edit(index, { replace_with: (e.target.value || null) as GradeCategory | null })}>
                  <option value="">Nothing</option>
                  {CATEGORIES.filter((category) => category !== row.category).map((category) => (
                    <option key={category} value={category}>{category}</option>
                  ))}
                </select>
              </td>
              <td>
                <button type="button" className="syllabusRemove" aria-label={`Remove ${row.category}`}
                  onClick={() => setRows(rows.filter((_, at) => at !== index))}>×</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {unused.length > 0 && (
        <select className="--input" value="" aria-label="Add a category"
          onChange={(e) => e.target.value && setRows([...rows, {
            category: e.target.value as GradeCategory, weight: 0, drop_lowest: 0, replace_with: null,
          }])}>
          <option value="">Add a category…</option>
          {unused.map((category) => <option key={category} value={category}>{category}</option>)}
        </select>
      )}
      {error && <p className="small-text error" role="alert">{error}</p>}
      <div className="flex justify-end gap-3 pt-4">
        <button type="button" className="buttons" onClick={save}
          disabled={saving || !label.trim() || rows.length === 0}>
          {saving ? "Saving…" : "Save scheme"}
        </button>
      </div>
    </Modal>
  );
}
