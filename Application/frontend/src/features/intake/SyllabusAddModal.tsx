import { useState } from "react";
import SyllabusRules, { confirmedRules, RuleDrafts } from "./SyllabusRules";
import Modal from "../../shared/components/Modal";
import { addToCourse, AddPreview, AddResult, previewAdd, readSyllabus } from "./api";
import { asBase64 } from "./file";
import "../../styles/budget.css";

interface SyllabusAddModalProps {
  readonly userId: string;
  readonly courseId: string;
  readonly onClose: () => void;
  /** Called after anything was added, so the course page reloads. */
  readonly onAdded: () => void;
}

/**
 * A syllabus adding to a course you already have -- add-only (Phase 1 D27).
 *
 * Only what the course lacks is offered, each ticked to add. What it already
 * has is listed so you can see it was recognised, and is never changed: not a
 * mark, a weight, a date or a name. Weights that differ are said, not applied.
 */
export default function SyllabusAddModal({ userId, courseId, onClose, onAdded }: SyllabusAddModalProps) {
  const [busy, setBusy] = useState<"reading" | "adding" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [parseId, setParseId] = useState<string | null>(null);
  const [preview, setPreview] = useState<AddPreview | null>(null);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [setSection, setSetSection] = useState(true);
  const [done, setDone] = useState<AddResult | null>(null);
  const [rules, setRules] = useState<RuleDrafts>({
    prerequisites: { text: "", note: "" }, corequisites: { text: "", note: "" },
  });

  async function choose(file: File | undefined) {
    if (!file) return;
    setBusy("reading");
    setError(null);
    try {
      const mediaType = file.type === "text/plain" ? "text/plain" : "application/pdf";
      const parsed = await readSyllabus(userId, file.name, mediaType, await asBase64(file));
      const result = await previewAdd(userId, parsed.id, courseId);
      setParseId(parsed.id);
      setPreview(result);
      setPicked(new Set(result.rows.flatMap((row, index) => (row.exists ? [] : [index]))));
      // Filled in from the syllabus only where you have no rule of your own:
      // yours is never replaced unless you type the replacement.
      setRules({
        prerequisites: { text: result.own_prerequisites ? "" : result.prerequisites?.text ?? "",
                         note: result.own_prerequisites ? "" : result.prerequisites?.note ?? "" },
        corequisites: { text: result.own_corequisites ? "" : result.corequisites?.text ?? "",
                        note: result.own_corequisites ? "" : result.corequisites?.note ?? "" },
      });
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Couldn't read that syllabus.");
    } finally {
      setBusy(null);
    }
  }

  function toggle(index: number) {
    const next = new Set(picked);
    if (next.has(index)) next.delete(index);
    else next.add(index);
    setPicked(next);
  }

  async function add() {
    if (!preview || !parseId) return;
    setBusy("adding");
    setError(null);
    try {
      const rows = preview.rows
        .filter((_, index) => picked.has(index))
        .map(({ name, category, due_date }) => ({ name, category, due_date }));
      const result = await addToCourse(userId, parseId, courseId, {
        rows, set_section: Boolean(preview.section_offer) && setSection, ...chosenRules,
      });
      setDone(result);
      if (result.added > 0 || result.section_set || (result.rules_filed ?? 0) > 0) onAdded();
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Couldn't add to the course.");
    } finally {
      setBusy(null);
    }
  }

  const sectionChange = Boolean(preview?.section_offer) && setSection;
  const chosenRules = confirmedRules(rules, {
    prerequisites: Boolean(preview?.prerequisites), corequisites: Boolean(preview?.corequisites),
  });
  const nothing = picked.size === 0 && !sectionChange && Object.keys(chosenRules).length === 0;

  return (
    <Modal title="Add from a syllabus" onClose={onClose} panelClassName="syllabusPanel">
      {done ? (
        <>
          <p role="status">
            {done.added === 1 ? "Added 1 assessment" : `Added ${done.added} assessments`}
            {done.skipped > 0 ? ` (${done.skipped} already on the course, left as they were)` : ""}
            {done.section_set ? ", and set the section" : ""}
            {(done.rules_filed ?? 0) > 0 ? ", and kept the prerequisites as yours" : ""}.
          </p>
          <div className="flex justify-end gap-3 pt-4">
            <button type="button" className="buttons" onClick={onClose}>Done</button>
          </div>
        </>
      ) : !preview ? (
        <>
          <label className="importFile">
            <span className="small-text muted">The course syllabus, as a PDF</span>
            <input type="file" accept=".pdf,application/pdf,.txt,text/plain" disabled={busy !== null}
              onChange={(event) => void choose(event.target.files?.[0])} aria-label="Syllabus file" />
          </label>
          {busy === "reading" && (
            <p className="small-text muted" role="status">Reading the syllabus… this can take up to a minute.</p>
          )}
        </>
      ) : (
        <>
          {preview.weight_notes.length > 0 && (
            <ul className="syllabusWarnings" aria-label="Weights that differ">
              {preview.weight_notes.map((note) => (
                <li key={note.category} className="small-text">
                  The syllabus gives {note.category} {note.syllabus}%; this course has {note.course}%. Weights
                  aren&apos;t changed here.
                </li>
              ))}
            </ul>
          )}
          {preview.unweighted.length > 0 && (
            <p className="small-text">
              {preview.unweighted.join(", ")} {preview.unweighted.length === 1 ? "has" : "have"} no weight on this
              course, so {preview.unweighted.length === 1 ? "its" : "their"} new rows won&apos;t count until you set
              one.
            </p>
          )}
          <ul className="syllabusAddRows" aria-label="Assessments from the syllabus">
            {preview.rows.map((row, index) => (
              <li key={`${row.category}-${row.name}-${index}`} className={row.exists ? "muted" : ""}>
                {row.exists ? (
                  <span className="small-text">
                    {row.name} · {row.category} — already on the course
                    {row.matched && row.matched !== row.name ? ` as "${row.matched}"` : ""}
                  </span>
                ) : (
                  <label>
                    <input type="checkbox" checked={picked.has(index)} onChange={() => toggle(index)}
                      aria-label={`Add ${row.name}`} />{" "}
                    {row.name} · {row.category}{row.due_date ? ` · ${row.due_date}` : ""}
                  </label>
                )}
              </li>
            ))}
          </ul>
          {preview.section_offer && (
            <label className="small-text">
              <input type="checkbox" checked={setSection} onChange={(e) => setSetSection(e.target.checked)} />{" "}
              Set this course&apos;s section to {preview.section_offer}
            </label>
          )}
          <SyllabusRules found={preview} drafts={rules} onChange={setRules}
            own={{ prerequisites: preview.own_prerequisites, corequisites: preview.own_corequisites }} />
          <div className="importFooter">
            <span className="small-text" role="status">Nothing already on the course is changed.</span>
            <button type="button" className="buttons" onClick={add} disabled={busy !== null || nothing}>
              {busy === "adding" ? "Adding…" : picked.size === 1 ? "Add 1 assessment" : `Add ${picked.size} assessments`}
            </button>
          </div>
        </>
      )}
      {error && <p className="small-text error" role="alert">{error}</p>}
    </Modal>
  );
}
