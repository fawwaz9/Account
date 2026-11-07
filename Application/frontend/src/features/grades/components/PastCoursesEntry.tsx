import { Fragment, useState } from "react";
import Modal from "../../../shared/components/Modal";
import { createCourse } from "../api";
import { CourseCreate, Semester } from "../types";
import { getErrorMessage } from "./AddCourseModal";

/** One row of the table as typed: strings, so a half-typed number isn't forced to 0. */
interface Row {
  readonly key: number;
  code: string;
  name: string;
  year: string;
  semester: Semester;
  credits: string;
  final: string;
  /** Why the server refused this row, kept beside it. */
  error?: string;
}

let nextKey = 0;

/** An empty row, starting from the term of the row above it. */
function blankRow(after?: Row): Row {
  return {
    key: nextKey++, code: "", name: "", year: after?.year ?? "1", semester: after?.semester ?? Semester.FALL,
    credits: "3", final: "",
  };
}

/** Whether a row has anything typed in it; blank rows are skipped on save. */
function touched(row: Row): boolean {
  return Boolean(row.code.trim() || row.name.trim() || row.final.trim());
}

/** What's missing from a row before it can be sent, or null. */
function problem(row: Row): string | null {
  const final = Number(row.final);
  if (row.code.trim().length < 3) return "Code needs at least 3 characters.";
  if (!row.name.trim()) return "Name is needed.";
  if (!row.final.trim() || !(final > 0 && final <= 100)) return "Final grade needs to be above 0 and at most 100.";
  const year = Number(row.year);
  if (!Number.isInteger(year) || year < 1 || year > 10) return "Year is 1 to 10.";
  const credits = Number(row.credits);
  if (!(credits >= 0.5 && credits <= 10)) return "Credits are 0.5 to 10.";
  return null;
}

/** The course a row becomes: its final grade and nothing else, so it's final-grade-only. */
function payload(row: Row): CourseCreate {
  return {
    code: row.code.trim(), name: row.name.trim(), year: Number(row.year), semester: row.semester,
    credits: Number(row.credits), final_grade: Number(row.final), required: true, professor: null, section: null,
    target_grade: null, category_weights: {}, start_date: null, end_date: null, no_final: false,
    transfer_credit: false, archived: false, links: [],
  };
}

/**
 * "Add past courses" (owner, 2026-11-07): a quick table for courses you have only a final
 * grade for, one row each. Every row becomes a final-grade-only course that counts like any
 * finished one; adding weights or marks later makes it a full course. Rows the server refuses
 * stay, with the reason beside them; the rest are added.
 */
export default function PastCoursesEntry({ userId, onAdded }: {
  readonly userId: string;
  /** Told after any course is added, so the page reloads its lists and figures. */
  readonly onAdded: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<Row[]>(() => [blankRow()]);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  function update(key: number, fields: Partial<Row>) {
    setRows((all) => all.map((row) => (row.key === key ? { ...row, ...fields, error: undefined } : row)));
  }

  function close() {
    setOpen(false);
    setRows([blankRow()]);
    setNote(null);
  }

  async function save() {
    const filled = rows.filter(touched);
    const checked = filled.map((row) => ({ ...row, error: problem(row) ?? undefined }));
    if (filled.length === 0 || checked.some((row) => row.error)) {
      setRows(checked.length ? checked : rows);
      setNote(filled.length === 0 ? "Type at least one course." : "Fix the rows marked below.");
      return;
    }
    setBusy(true);
    setNote(null);
    const refused: Row[] = [];
    let added = 0;
    // One at a time, in order, so each refusal sits beside its own row.
    for (const row of checked) {
      try {
        await createCourse(userId, payload(row));
        added += 1;
      } catch (err) {
        refused.push({ ...row, error: getErrorMessage(err) });
      }
    }
    setBusy(false);
    if (added > 0) onAdded();
    if (refused.length === 0) {
      close();
      return;
    }
    setRows(refused);
    setNote(`Added ${added} of ${checked.length}. The rest weren't added:`);
  }

  return (
    <>
      <button type="button" className="buttons addCourseButton" onClick={() => setOpen(true)}>
        Add past courses
      </button>
      {open && (
        <Modal title="Add past courses" onClose={close} panelClassName="widePopup">
          <p className="small-text">
            Only have the final grades? One row per course. Each counts toward your averages and degree like any
            finished course, and you can add its weights and marks later.
          </p>
          <table className="pastCoursesTable">
            <thead>
              <tr>
                <th>Code</th><th>Name</th><th>Year</th><th>Term</th><th>Credits</th><th>Final %</th><th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <Fragment key={row.key}>
                  <tr>
                    <td>
                      <input className="calInput" aria-label={`Row ${index + 1} code`} value={row.code}
                        placeholder="CPSC 110" maxLength={20} onChange={(e) => update(row.key, { code: e.target.value })} />
                    </td>
                    <td>
                      <input className="calInput" aria-label={`Row ${index + 1} name`} value={row.name}
                        placeholder="Computation, Programs and Programming" maxLength={100}
                        onChange={(e) => update(row.key, { name: e.target.value })} />
                    </td>
                    <td>
                      <input className="calInput" aria-label={`Row ${index + 1} year`} type="number" min={1} max={10}
                        value={row.year} onChange={(e) => update(row.key, { year: e.target.value })} />
                    </td>
                    <td>
                      <select className="calInput" aria-label={`Row ${index + 1} term`} value={row.semester}
                        onChange={(e) => update(row.key, { semester: e.target.value as Semester })}>
                        {Object.values(Semester).map((term) => <option key={term} value={term}>{term}</option>)}
                      </select>
                    </td>
                    <td>
                      <input className="calInput" aria-label={`Row ${index + 1} credits`} type="number" min={0.5} max={10}
                        step={0.5} value={row.credits} onChange={(e) => update(row.key, { credits: e.target.value })} />
                    </td>
                    <td>
                      <input className="calInput" aria-label={`Row ${index + 1} final grade`} type="number" min={0}
                        max={100} step="any" value={row.final} onChange={(e) => update(row.key, { final: e.target.value })} />
                    </td>
                    <td>
                      {rows.length > 1 && (
                        <button type="button" className="courseLinkAdd" aria-label={`Remove row ${index + 1}`}
                          onClick={() => setRows((all) => all.filter((r) => r.key !== row.key))}>
                          ×
                        </button>
                      )}
                    </td>
                  </tr>
                  {row.error && (
                    <tr>
                      <td colSpan={7} className="pastCoursesError" role="alert">Row {index + 1}: {row.error}</td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
          {note && <p className="small-text">{note}</p>}
          <div className="catalogueActions">
            <button type="button" className="calButton"
              onClick={() => setRows((all) => [...all, blankRow(all[all.length - 1])])}>
              Add row
            </button>
            <button type="button" className="calButton" onClick={close}>Cancel</button>
            <button type="button" className="calButton calButtonPrimary" disabled={busy} onClick={() => void save()}>
              {busy ? "Adding…" : "Add courses"}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
