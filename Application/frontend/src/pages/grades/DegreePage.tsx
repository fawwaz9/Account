import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../app/auth/AuthContext";
import Modal from "../../shared/components/Modal";
import HelpTip from "../../shared/components/HelpTip";
import DeleteConfirmModal from "../../features/grades/components/DeleteConfirmModal";
import {
  Counted,
  createEquivalence,
  createRequirement,
  DegreeAudit,
  deleteEquivalence,
  deleteRequirement,
  Equivalence,
  fetchAudit,
  Requirement,
  RequirementResult,
  updateEquivalence,
  updateRequirement,
} from "../../features/degree/api";

const STATUS_WORD: Record<Counted["status"], string> = {
  completed: "done",
  in_progress: "in progress",
  planned: "planned",
};

type Removing = { kind: "requirement"; row: Requirement } | { kind: "equivalence"; row: Equivalence };

/**
 * The degree audit -- Phase 1 item 5 (D31).
 *
 * Your requirements, entered once from your programme page, against your
 * courses. Each requirement says what met it and with which course, so a
 * wrong answer can be traced to the course or the mapping behind it.
 */
export default function DegreePage() {
  const { user } = useAuth();
  const [audit, setAudit] = useState<DegreeAudit | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Requirement | "new" | null>(null);
  const [mapping, setMapping] = useState<Equivalence | "new" | null>(null);
  const [removing, setRemoving] = useState<Removing | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const latest = useRef(0);

  useEffect(() => {
    if (!user) return;
    const ticket = ++latest.current;
    fetchAudit(user.id)
      .then((result) => { if (ticket === latest.current) { setAudit(result); setLoadError(null); } })
      .catch(() => { if (ticket === latest.current) setLoadError("Couldn't load the audit."); });
    // The id, not the object: a fresh object for the same user must not refetch.
  }, [user?.id, refresh]);

  const reload = () => setRefresh((n) => n + 1);

  async function confirmRemove() {
    if (!user || !removing) return;
    setRemoveBusy(true);
    setRemoveError(null);
    try {
      if (removing.kind === "requirement") await deleteRequirement(user.id, removing.row.id);
      else await deleteEquivalence(user.id, removing.row.id);
      setRemoving(null);
      reload();
    } catch {
      setRemoveError("Couldn't remove it.");
    } finally {
      setRemoveBusy(false);
    }
  }

  if (!user) return null;

  return (
    <div className="container degreePage">
      <div className="gradesMenu">
        <h1 className="gradesTitle">
          Degree audit{" "}
          <HelpTip label="How the audit works">
            Enter your programme&apos;s requirements once, from your programme page. A course counts toward one
            requirement, unless that requirement shares (breadth usually does). &quot;These courses&quot;
            requirements are filled before &quot;credits from&quot; ones, and finished courses before ones in
            progress. A course that didn&apos;t pass counts nowhere.
          </HelpTip>
        </h1>
        <Link to="/grades" className="calButton">Back to grades</Link>
      </div>

      {loadError && <p className="small-text error" role="alert">{loadError}</p>}

      {audit && (
        <>
          <p className="degreeTotals">
            <strong>{audit.credits_completed}</strong> of {audit.credit_target} credits done
            {audit.credits_in_progress > 0 ? `, ${audit.credits_in_progress} in progress` : ""}
          </p>

          <section aria-label="Requirements">
            <div className="sectionHeading">
              <h2>Requirements</h2>
              <button type="button" className="buttons addCourseButton" onClick={() => setEditing("new")}>
                Add requirement
              </button>
            </div>
            {audit.requirements.map((result) => (
              <RequirementCard
                key={result.requirement.id}
                result={result}
                onEdit={() => setEditing(result.requirement)}
                onRemove={() => { setRemoveError(null); setRemoving({ kind: "requirement", row: result.requirement }); }}
              />
            ))}
          </section>

          <section aria-label="Course mappings" className="degreeMappings">
            <div className="sectionHeading">
              <h2>
                Courses that count as others{" "}
                <HelpTip label="What a mapping is">
                  Transfer credits and other-campus courses: &quot;COSC 111 + COSC 121 count as CPSC 110&quot;,
                  or one course counting as several. A mapping with several courses applies once all of them are on
                  your record, counts as done when all of them are, and stands in for them, so nothing counts
                  twice. Credits, if set, replace the
                  courses&apos; total, for partial credit.
                </HelpTip>
              </h2>
              <button type="button" className="buttons addCourseButton" onClick={() => setMapping("new")}>
                Add mapping
              </button>
            </div>
            <ul className="degreeList">
              {audit.equivalences.map((e) => (
                <li key={e.id}>
                  <span>
                    {e.from_codes.join(" + ")} count as {e.counts_as.join(", ")}
                    {e.credits !== null ? ` (${e.credits} credits)` : ""}
                    {e.note ? <span className="small-text muted"> · {e.note}</span> : null}
                  </span>
                  <span className="schemeActions">
                    <button type="button" className="calButton" onClick={() => setMapping(e)}>Edit</button>
                    <button
                      type="button"
                      className="calButton"
                      onClick={() => { setRemoveError(null); setRemoving({ kind: "equivalence", row: e }); }}
                    >
                      Remove
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          </section>

          {audit.not_counted.length > 0 && (
            <section aria-label="Not counted">
              <h2>Done, but counted toward nothing</h2>
              <p className="small-text">{audit.not_counted.map((c) => c.label).join(", ")}</p>
            </section>
          )}
          {audit.failed.length > 0 && (
            <section aria-label="Did not pass">
              <h2>Didn&apos;t pass, so not counted</h2>
              <p className="small-text">{audit.failed.join(", ")}</p>
            </section>
          )}
        </>
      )}

      {editing && (
        <RequirementEditor
          userId={user.id}
          editing={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); reload(); }}
        />
      )}
      {mapping && (
        <EquivalenceEditor
          userId={user.id}
          editing={mapping === "new" ? null : mapping}
          onClose={() => setMapping(null)}
          onSaved={() => { setMapping(null); reload(); }}
        />
      )}
      <DeleteConfirmModal
        open={removing !== null}
        title={removing?.kind === "requirement" ? "Remove this requirement?" : "Remove this mapping?"}
        message={removing
          ? removing.kind === "requirement"
            ? `"${removing.row.name}" will be removed from your audit. Your courses are not touched.`
            : `${removing.row.from_codes.join(" + ")} will stop counting as ${removing.row.counts_as.join(", ")}. Your courses are not touched.`
          : ""}
        onConfirm={confirmRemove}
        onCancel={() => setRemoving(null)}
        submitting={removeBusy}
        error={removeError}
        confirmLabel="Remove"
      />
    </div>
  );
}

function RequirementCard({ result, onEdit, onRemove }: {
  readonly result: RequirementResult;
  readonly onEdit: () => void;
  readonly onRemove: () => void;
}) {
  const { requirement } = result;
  const needed = requirement.credits_needed ?? 0;
  const progress = requirement.kind === "credits"
    ? `${result.credits_completed} of ${needed} credits${result.credits_in_progress
      ? `, ${result.credits_in_progress} in progress` : ""}`
    : `${result.items.filter((i) => i.met_by?.status === "completed").length} of ${result.items.length} done`;
  return (
    <article className={result.done ? "degreeCard degreeDone" : "degreeCard"}>
      <header>
        <h3>{requirement.name}</h3>
        <span className="small-text">{progress}{requirement.shares ? " · shares courses" : ""}</span>
        <span className="schemeActions">
          <button type="button" className="calButton" onClick={onEdit}>Edit</button>
          <button type="button" className="calButton" onClick={onRemove}>Remove</button>
        </span>
      </header>
      {requirement.kind === "courses" ? (
        <ul className="degreeList">
          {result.items.map((line) => (
            <li key={line.item} className={line.met_by ? `degree--${line.met_by.status}` : "degree--missing"}>
              <span>{line.item}</span>
              <span className="small-text">
                {line.met_by ? `${line.met_by.label} · ${STATUS_WORD[line.met_by.status]}` : "missing"}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <>
          <p className="small-text muted">From {requirement.items.join(", ")}</p>
          {result.counted.length > 0 && (
            <ul className="degreeList">
              {result.counted.map((c) => (
                <li key={c.label} className={`degree--${c.status}`}>
                  <span>{c.label}</span>
                  <span className="small-text">{c.credits} credits · {STATUS_WORD[c.status]}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </article>
  );
}

function lines(text: string): string[] {
  return text.split("\n").map((line) => line.trim()).filter(Boolean);
}

function RequirementEditor({ userId, editing, onClose, onSaved }: {
  readonly userId: string;
  readonly editing: Requirement | null;
  readonly onClose: () => void;
  readonly onSaved: () => void;
}) {
  const [name, setName] = useState(editing?.name ?? "");
  const [kind, setKind] = useState<Requirement["kind"]>(editing?.kind ?? "courses");
  const [items, setItems] = useState((editing?.items ?? []).join("\n"));
  const [credits, setCredits] = useState(editing?.credits_needed?.toString() ?? "");
  const [shares, setShares] = useState(editing?.shares ?? false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const body = {
        name: name.trim(), kind, items: lines(items), shares,
        credits_needed: kind === "credits" ? Number(credits) || null : null,
      };
      if (editing) await updateRequirement(userId, editing.id, body);
      else await createRequirement(userId, body);
      onSaved();
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Couldn't save the requirement.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title={editing ? "Edit requirement" : "Add a requirement"} onClose={onClose}>
      <label className="calField">
        <span className="calFieldLabel">Name</span>
        <input className="--input" value={name} onChange={(e) => setName(e.target.value)}
          placeholder="Upper-level CPSC" aria-label="Requirement name" />
      </label>
      <label className="calField">
        <span className="calFieldLabel">Kind</span>
        <select className="--input" value={kind} aria-label="Kind"
          onChange={(e) => setKind(e.target.value as Requirement["kind"])}>
          <option value="courses">These courses, all of them</option>
          <option value="credits">A number of credits from</option>
        </select>
      </label>
      <label className="calField">
        <span className="calFieldLabel">
          {kind === "courses" ? "Courses, one per line" : "Courses or patterns, one per line"}{" "}
          <HelpTip label="What can go on a line">
            A code (CPSC 110), alternatives (MATH 100 | MATH 180), a level (CPSC 3xx), a floor (CPSC 300+ or
            300+), or a whole subject (CPSC).
          </HelpTip>
        </span>
        <textarea className="--input" rows={5} value={items} onChange={(e) => setItems(e.target.value)}
          aria-label="Courses or patterns"
          placeholder={kind === "courses" ? "CPSC 110\nMATH 100 | MATH 180" : "CPSC 3xx"} />
      </label>
      {kind === "credits" && (
        <label className="calField">
          <span className="calFieldLabel">Credits needed</span>
          <input className="--input" type="number" min={0.5} step={0.5} value={credits}
            onChange={(e) => setCredits(e.target.value)} aria-label="Credits needed" />
        </label>
      )}
      <label className="small-text">
        <input type="checkbox" checked={shares} onChange={(e) => setShares(e.target.checked)} />{" "}
        Courses here may also count toward other requirements
      </label>
      {error && <p className="small-text error" role="alert">{error}</p>}
      <div className="flex justify-end gap-3 pt-4">
        <button
          type="button"
          className="buttons"
          onClick={save}
          disabled={saving || !name.trim() || lines(items).length === 0 || (kind === "credits" && !Number(credits))}
        >
          {saving ? "Saving…" : "Save requirement"}
        </button>
      </div>
    </Modal>
  );
}

function codes(text: string): string[] {
  return text.split(/[,+\n]/).map((code) => code.trim()).filter(Boolean);
}

function EquivalenceEditor({ userId, editing, onClose, onSaved }: {
  readonly userId: string;
  readonly editing: Equivalence | null;
  readonly onClose: () => void;
  readonly onSaved: () => void;
}) {
  const [from, setFrom] = useState((editing?.from_codes ?? []).join(" + "));
  const [to, setTo] = useState((editing?.counts_as ?? []).join(", "));
  const [credits, setCredits] = useState(editing?.credits?.toString() ?? "");
  const [note, setNote] = useState(editing?.note ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const body = {
        from_codes: codes(from), counts_as: codes(to),
        credits: credits.trim() ? Number(credits) : null, note: note.trim() || null,
      };
      if (editing) await updateEquivalence(userId, editing.id, body);
      else await createEquivalence(userId, body);
      onSaved();
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Couldn't save the mapping.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title={editing ? "Edit mapping" : "Add a mapping"} onClose={onClose}>
      <label className="calField">
        <span className="calFieldLabel">Courses you took</span>
        <input className="--input" value={from} onChange={(e) => setFrom(e.target.value)}
          placeholder="COSC 111 + COSC 121" aria-label="Courses you took" />
      </label>
      <label className="calField">
        <span className="calFieldLabel">Count as</span>
        <input className="--input" value={to} onChange={(e) => setTo(e.target.value)}
          placeholder="CPSC 110" aria-label="Count as" />
      </label>
      <label className="calField">
        <span className="calFieldLabel">Credits, if not the courses&apos; total</span>
        <input className="--input" type="number" min={0.5} step={0.5} value={credits}
          onChange={(e) => setCredits(e.target.value)} aria-label="Credits" />
      </label>
      <label className="calField">
        <span className="calFieldLabel">Note</span>
        <input className="--input" value={note} onChange={(e) => setNote(e.target.value)}
          placeholder="From the transfer credit letter" aria-label="Note" />
      </label>
      {error && <p className="small-text error" role="alert">{error}</p>}
      <div className="flex justify-end gap-3 pt-4">
        <button
          type="button"
          className="buttons"
          onClick={save}
          disabled={saving || codes(from).length === 0 || codes(to).length === 0}
        >
          {saving ? "Saving…" : "Save mapping"}
        </button>
      </div>
    </Modal>
  );
}
