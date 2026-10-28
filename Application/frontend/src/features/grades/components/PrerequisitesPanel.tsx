import { useEffect, useState } from "react";
import { checkPrerequisiteText, deleteOwnPrerequisite, fetchPrerequisites, saveOwnPrerequisite } from "../api";
import { PrerequisiteKind, PrerequisiteKindName, PrerequisiteSide, Prerequisites, RuleResult, RuleStatus } from "../types";
import { getErrorMessage } from "./AddCourseModal";
import HelpTip from "../../../shared/components/HelpTip";

/** Each rule status in words, never colour alone; "not met" says exceptions are made. */
export const STATUS_WORDS: Record<RuleStatus, string> = {
  met: "Met",
  on_track: "On track, if what's under way goes to plan",
  not_met: "Not met, and exceptions are sometimes made",
};
/** The symbol drawn for each rule status. */
const MARK: Record<RuleStatus, string> = { met: "✓", on_track: "…", not_met: "✗" };
/** The heading for each requisite kind. */
const KIND_TITLE: Record<PrerequisiteKindName, string> = {
  prerequisite: "Prerequisites",
  corequisite: "Co-requisites",
};

/** Where a version of a rule came from, in words. */
function sourceWords(side: PrerequisiteSide) {
  switch (side.source) {
    case "typed": return "Your version";
    case "syllabus": return "Your version, from your syllabus";
    case "reviewed": return "Shared, reviewed";
    case "ubc-calendar": return "Shared, from the UBC calendar";
  }
}

/** What each review state of your shared submission means. */
const REVIEW_WORDS: Record<string, string> = {
  pending: "waiting for review before anyone else sees it",
  accepted: "accepted into the shared catalogue",
  rejected: "kept as yours only",
};

/** One node of an evaluated rule: a single requirement, or an all-of or one-of group. */
function Leaf({ result }: { readonly result: RuleResult }) {
  if (result.parts.length === 0) {
    return (
      <li className={`ruleLeaf ruleLeaf--${result.status}`}>
        <span aria-hidden="true">{MARK[result.status]}</span>{" "}
        <span className="srOnly">{result.status === "met" ? "met:" : result.status === "on_track" ? "on track:" : "not met:"}</span>
        {result.text}
        {result.detail && <span className="muted"> · {result.detail}</span>}
      </li>
    );
  }
  const group = result.group === "any" ? "One of" : "All of";
  return (
    <li className={`ruleLeaf ruleLeaf--${result.status}`}>
      <span aria-hidden="true">{MARK[result.status]}</span> {group}:
      <ul className="ruleTree">
        {result.parts.map((part, index) => <Leaf key={index} result={part} />)}
      </ul>
    </li>
  );
}

/** One version of a rule: its status, its tree, and where it came from. */
function Side({ side }: { readonly side: PrerequisiteSide }) {
  return (
    <div className="prereqSide">
      <p className={`prereqStatus prereqStatus--${side.result.status}`}>{STATUS_WORDS[side.result.status]}</p>
      <ul className="ruleTree">
        <Leaf result={side.result} />
      </ul>
      {side.note && <p className="small-text">{side.note}</p>}
      <p className="small-text muted">
        {sourceWords(side)}
        {side.review && ` · ${REVIEW_WORDS[side.review]}`}
        {side.session && ` · ${side.session}`}
      </p>
      {side.source_text && (
        <blockquote className="prereqQuote small-text">{side.source_text}</blockquote>
      )}
    </div>
  );
}

/** The kind being edited, your current version, and save and cancel callbacks. */
interface EditorProps {
  readonly userId: string;
  readonly courseId: string;
  readonly kind: PrerequisiteKindName;
  readonly current: PrerequisiteSide | null;
  readonly onSaved: (next: Prerequisites) => void;
  readonly onCancel: () => void;
}

/** Form for your own rule of one kind; the typed text is read back when the field loses focus. */
function Editor({ userId, courseId, kind, current, onSaved, onCancel }: EditorProps) {
  const [text, setText] = useState(current?.text ?? "");
  const [note, setNote] = useState(current?.note ?? "");
  const [reading, setReading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function check() {
    if (!text.trim()) return;
    try {
      setReading((await checkPrerequisiteText(userId, text)).text);
      setError(null);
    } catch (err) {
      setReading(null);
      setError(getErrorMessage(err));
    }
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      onSaved(await saveOwnPrerequisite(userId, courseId, { kind, text, note: note.trim() || null }));
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  const id = `prereq-${kind}-${courseId}`;
  return (
    <form className="prereqEditor" onSubmit={(event) => { event.preventDefault(); void save(); }}>
      <label htmlFor={id}>Your {kind === "prerequisite" ? "prerequisites" : "co-requisites"}</label>
      <input id={id} value={text} maxLength={300} placeholder="CPSC 210 and one of MATH 200, MATH 217"
             onChange={(event) => { setText(event.target.value); setReading(null); }} onBlur={() => void check()} />
      <p className="small-text muted">
        Use <em>and</em>, <em>or</em>, <em>one of A, B</em>, <em>6 credits of MATH 1xx</em>,{" "}
        <em>CPSC 210 with 64%</em>.
      </p>
      {reading && <p className="small-text" role="status">Reads as: {reading}</p>}
      <label htmlFor={`${id}-note`}>Anything else (year standing, permission)</label>
      <input id={`${id}-note`} value={note} maxLength={300} onChange={(event) => setNote(event.target.value)} />
      {error && <p className="small-text error" role="alert">{error}</p>}
      <div className="catalogueActions">
        <button type="submit" className="calButton" disabled={saving || !text.trim()}>Save</button>
        <button type="button" className="calButton" onClick={onCancel} disabled={saving}>Cancel</button>
      </div>
    </form>
  );
}

/** The course whose requisites to show. */
interface PanelProps {
  readonly userId: string;
  readonly courseId: string;
}

/**
 * A course's requisites, met or not: your version applies when you have one, the shared one below.
 * Advisory only; renders nothing if the read fails.
 */
export default function PrerequisitesPanel({ userId, courseId }: PanelProps) {
  const [data, setData] = useState<Prerequisites | null>(null);
  const [editing, setEditing] = useState<PrerequisiteKindName | null>(null);
  // Removing yours is permanent, so it asks first: the inline pair, as on a
  // list you are already editing.
  const [removing, setRemoving] = useState<PrerequisiteKindName | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchPrerequisites(userId, courseId)
      .then((found) => { if (!cancelled) setData(found); })
      .catch(() => { if (!cancelled) setData(null); });
    return () => { cancelled = true; };
  }, [userId, courseId]);

  if (!data) return null;

  async function remove(kind: PrerequisiteKindName) {
    setError(null);
    try {
      setData(await deleteOwnPrerequisite(userId, courseId, kind));
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setRemoving(null);
    }
  }

  const shown = data.kinds.filter((k) => k.yours || k.shared || editing === k.kind);
  const missing = data.kinds.filter((k) => !k.yours && editing !== k.kind);

  function block(entry: PrerequisiteKind) {
    const main = entry.applies === "yours" ? entry.yours : entry.shared;
    const other = entry.applies === "yours" ? entry.shared : null;
    return (
      <div className="prereqKind" key={entry.kind}>
        <h3>{KIND_TITLE[entry.kind]}</h3>
        {editing === entry.kind ? (
          <Editor userId={userId} courseId={courseId} kind={entry.kind} current={entry.yours}
                  onSaved={(next) => { setData(next); setEditing(null); }} onCancel={() => setEditing(null)} />
        ) : (
          <>
            {main && <Side side={main} />}
            {other && (
              <details className="prereqOther">
                <summary className="small-text">The shared version: {other.text}</summary>
                <Side side={other} />
              </details>
            )}
            {entry.yours && removing !== entry.kind && (
              <div className="catalogueActions">
                <button type="button" className="courseLinkAdd" onClick={() => setEditing(entry.kind)}>Edit yours</button>
                <button type="button" className="courseLinkAdd" onClick={() => setRemoving(entry.kind)}>
                  Remove yours
                </button>
              </div>
            )}
            {entry.yours && removing === entry.kind && (
              <div className="catalogueActions">
                <span className="small-text">Remove your version for good?</span>
                <button type="button" className="calButton calButtonDanger" onClick={() => void remove(entry.kind)}>
                  Yes, delete
                </button>
                <button type="button" className="calButton" onClick={() => setRemoving(null)}>Keep</button>
              </div>
            )}
          </>
        )}
      </div>
    );
  }

  return (
    <section className="prereqPanel" aria-label="Prerequisites">
      <div className="sectionHeading">
        <h2>Prerequisites</h2>
        <HelpTip label="How prerequisites work here">
          A warning, never a block: exceptions are sometimes made, so nothing is ever
          refused because one is unmet. Your own version counts for you straight away.
          It reaches others only after review, as the rule alone, never your syllabus's
          wording.
        </HelpTip>
      </div>
      {shown.map(block)}
      {error && <p className="small-text error" role="alert">{error}</p>}
      {missing.length > 0 && (
        <div className="catalogueActions">
          {shown.length === 0 && <span className="small-text muted">None recorded.</span>}
          {missing.map((k) => (
            <button key={k.kind} type="button" className="courseLinkAdd" onClick={() => setEditing(k.kind)}>
              Add your {k.kind === "prerequisite" ? "prerequisites" : "co-requisites"}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
