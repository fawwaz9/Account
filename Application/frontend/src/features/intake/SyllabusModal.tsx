import { useMemo, useState } from "react";
import Modal from "../../shared/components/Modal";
import { GradeCategory } from "../grades/types";
import { applySyllabus, Assessment, ParseResult, readSyllabus } from "./api";
import { asBase64 } from "./file";

interface SyllabusModalProps {
  readonly userId: string;
  readonly onClose: () => void;
  /** Called with the new course's id once it is built. */
  readonly onBuilt: (courseId: string) => void;
}

const CATEGORIES = Object.values(GradeCategory);

/**
 * A syllabus in, a course out -- Phase 1 item 1.
 *
 * The verification screen is the product (account-vision.md §13.8): what was
 * read is laid out with every field editable, the checks the server made sit
 * on top, and nothing is created until "Create course". The weights' total is
 * live and the button waits for 100%, because a gradebook whose weights do not
 * add up projects every grade wrong.
 */
export default function SyllabusModal({ userId, onClose, onBuilt }: SyllabusModalProps) {
  const [busy, setBusy] = useState<"reading" | "building" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [parsed, setParsed] = useState<ParseResult | null>(null);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [section, setSection] = useState("");
  const [professor, setProfessor] = useState("");
  const [credits, setCredits] = useState("3");
  const [rows, setRows] = useState<Assessment[]>([]);

  async function choose(file: File | undefined) {
    if (!file) return;
    setBusy("reading");
    setError(null);
    try {
      const content = await asBase64(file);
      const mediaType = file.type === "text/plain" ? "text/plain" : "application/pdf";
      const result = await readSyllabus(userId, file.name, mediaType, content);
      setParsed(result);
      setCode(result.extract.course_code);
      setName(result.extract.course_name);
      setSection(result.extract.section ?? "");
      setProfessor(result.extract.professor ?? "");
      setRows(result.extract.assessments);
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Couldn't read that syllabus.");
    } finally {
      setBusy(null);
    }
  }

  const total = useMemo(
    () => rows.filter((row) => row.category !== GradeCategory.BONUS)
      .reduce((sum, row) => sum + (Number.isFinite(row.weight) ? row.weight : 0), 0),
    [rows],
  );
  const adds = Math.abs(total - 100) <= 0.5;

  function edit(index: number, change: Partial<Assessment>) {
    setRows(rows.map((row, at) => (at === index ? { ...row, ...change } : row)));
  }

  async function build() {
    if (!parsed) return;
    setBusy("building");
    setError(null);
    try {
      const result = await applySyllabus(userId, parsed.id, {
        course_code: code.trim(),
        course_name: name.trim(),
        section: section.trim() || null,
        professor: professor.trim() || null,
        credits: Number(credits) || 3,
        assessments: rows.map((row) => ({ ...row, name: row.name.trim() })),
      });
      onBuilt(result.course_id);
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Couldn't create the course.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Modal title="Add a course from its syllabus" onClose={onClose} panelClassName="syllabusPanel">
      {!parsed && (
        <label className="importFile">
          <span className="small-text muted">The course syllabus, as a PDF</span>
          <input
            type="file"
            accept=".pdf,application/pdf,.txt,text/plain"
            onChange={(event) => void choose(event.target.files?.[0])}
            disabled={busy !== null}
            aria-label="Syllabus file"
          />
        </label>
      )}
      {busy === "reading" && (
        <p className="small-text muted" role="status">Reading the syllabus… this can take up to a minute.</p>
      )}
      {error && <p className="small-text error" role="alert">{error}</p>}

      {parsed && (
        <>
          {parsed.warnings.length > 0 && (
            <ul className="syllabusWarnings" aria-label="Check these">
              {parsed.warnings.map((warning) => <li key={warning} className="small-text">{warning}</li>)}
            </ul>
          )}

          <div className="syllabusCourse">
            <label>
              <span className="small-text muted">Code</span>
              <input className="--input" value={code} onChange={(e) => setCode(e.target.value)} aria-label="Course code" />
            </label>
            <label className="syllabusWide">
              <span className="small-text muted">Name</span>
              <input className="--input" value={name} onChange={(e) => setName(e.target.value)} aria-label="Course name" />
            </label>
            <label>
              <span className="small-text muted">Section</span>
              <input className="--input" value={section} maxLength={20} placeholder="101"
                onChange={(e) => setSection(e.target.value)} aria-label="Section" />
            </label>
            <label>
              <span className="small-text muted">Professor</span>
              <input className="--input" value={professor} onChange={(e) => setProfessor(e.target.value)} aria-label="Professor" />
            </label>
            <label>
              <span className="small-text muted">Credits</span>
              <input className="--input" type="number" min={0.5} max={10} step={0.5} value={credits}
                onChange={(e) => setCredits(e.target.value)} aria-label="Credits" />
            </label>
          </div>

          <div className="importTable">
            <table>
              <thead>
                <tr>
                  <th scope="col">What</th>
                  <th scope="col">Category</th>
                  <th scope="col">Weight %</th>
                  <th scope="col">How many</th>
                  <th scope="col">Date</th>
                  <th scope="col">TBA</th>
                  <th scope="col" aria-label="Remove" />
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={index}>
                    <td>
                      <input className="--input" value={row.name} aria-label={`Name of row ${index + 1}`}
                        onChange={(e) => edit(index, { name: e.target.value })} />
                    </td>
                    <td>
                      <select className="--input" value={row.category} aria-label={`Category of row ${index + 1}`}
                        onChange={(e) => edit(index, { category: e.target.value as GradeCategory })}>
                        {CATEGORIES.map((category) => <option key={category} value={category}>{category}</option>)}
                      </select>
                    </td>
                    <td>
                      <input className="--input syllabusNumber" type="number" min={0} max={100} step="0.5"
                        value={row.weight} aria-label={`Weight of row ${index + 1}`}
                        onChange={(e) => edit(index, { weight: Number(e.target.value) })} />
                    </td>
                    <td>
                      <input className="--input syllabusNumber" type="number" min={1} max={60}
                        value={row.count} aria-label={`How many in row ${index + 1}`}
                        onChange={(e) => edit(index, { count: Math.max(1, Number(e.target.value) || 1) })} />
                    </td>
                    <td>
                      <input className="--input" type="date" value={row.due_date ?? ""}
                        disabled={row.date_tba} aria-label={`Date of row ${index + 1}`}
                        onChange={(e) => edit(index, { due_date: e.target.value || null })} />
                    </td>
                    <td>
                      <input type="checkbox" checked={row.date_tba} aria-label={`Row ${index + 1} is TBA`}
                        onChange={(e) => edit(index, { date_tba: e.target.checked,
                          due_date: e.target.checked ? null : row.due_date })} />
                    </td>
                    <td>
                      <button type="button" className="syllabusRemove" aria-label={`Remove row ${index + 1}`}
                        onClick={() => setRows(rows.filter((_, at) => at !== index))}>
                        ×
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <button type="button" className="syllabusAdd"
            onClick={() => setRows([...rows, { name: "", category: GradeCategory.OTHER, weight: 0, count: 1,
              due_date: null, date_tba: false }])}>
            Add a row
          </button>

          <div className="importFooter">
            <span className={`small-text${adds ? "" : " syllabusOff"}`} role="status">
              Weights add up to {Math.round(total * 100) / 100}%{adds ? "" : " — they need to add up to 100%"}
            </span>
            <button
              type="button"
              className="buttons"
              onClick={build}
              disabled={busy !== null || !adds || !code.trim() || !name.trim()
                || rows.length === 0 || rows.some((row) => !row.name.trim())}
            >
              {busy === "building" ? "Creating…" : "Create course"}
            </button>
          </div>
        </>
      )}
    </Modal>
  );
}
