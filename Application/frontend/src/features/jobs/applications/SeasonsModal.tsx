import { useState } from "react";
import Modal from "../../../shared/components/Modal";
import DeleteConfirmModal from "../../grades/components/DeleteConfirmModal";
import { createSeason, deleteSeason, updateSeason } from "./api";
import { Season, SeasonInput } from "./types";
import { seasonSpan } from "./seasons";
import { useAuth } from "../../../app/auth/AuthContext";

/** Props for the seasons dialog. */
interface Props {
  readonly open: boolean;
  readonly seasons: Season[];
  readonly onClose: () => void;
  /** Called after a change, with the season saved if there was one. */
  readonly onSaved: (season?: Season) => void;
}

/** An empty season form. */
const BLANK: SeasonInput = { name: "", starts: "", ends: "" };

/**
 * List, add, rename and delete recruiting seasons, each a named range of months.
 * A season only groups applications by applied date, so deleting one deletes no application.
 */
export default function SeasonsModal({ open, seasons, onClose, onSaved }: Props) {
  const { user } = useAuth();
  const [form, setForm] = useState<SeasonInput>(BLANK);
  const [editing, setEditing] = useState<Season | null>(null);
  const [removing, setRemoving] = useState<Season | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  function startEdit(season: Season) {
    setEditing(season);
    setForm({ name: season.name, starts: season.starts, ends: season.ends });
    setError(null);
  }

  function reset() {
    setEditing(null);
    setForm(BLANK);
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;
    if (form.ends < form.starts) {
      setError("A season ends on or after the month it starts.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const saved = editing
        ? await updateSeason(user.id, editing.id, form)
        : await createSeason(user.id, form);
      reset();
      onSaved(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the season");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Modal title="Seasons" onClose={onClose}>
        <p className="small-text muted">
          A season covers the applications you sent in its months, the last month whole. Seasons may overlap.
        </p>

        {seasons.length > 0 && (
          <ul className="appSeasonList">
            {seasons.map((season) => (
              <li key={season.id} className="appSeasonRow">
                <span className="appRowTitle">{season.name}</span>
                <span className="small-text muted">{seasonSpan(season)}</span>
                <span className="appSeasonActions">
                  <button type="button" className="calButton" onClick={() => startEdit(season)}
                    aria-label={`Edit ${season.name}`}>Edit</button>
                  <button type="button" className="calButton" onClick={() => setRemoving(season)}
                    aria-label={`Delete ${season.name}`}>Delete</button>
                </span>
              </li>
            ))}
          </ul>
        )}

        <form className="calForm" onSubmit={save}>
          <div className="calRow">
            <label className="calField">
              <span className="calFieldLabel">{editing ? "Season" : "New season"}</span>
              <input className="calInput" value={form.name} required placeholder="Summer 2027 co-op"
                onChange={(e) => setForm((was) => ({ ...was, name: e.target.value }))} />
            </label>
          </div>
          <div className="calRow">
            <label className="calField">
              <span className="calFieldLabel">From</span>
              <input type="month" className="calInput" value={form.starts} required
                onChange={(e) => setForm((was) => ({ ...was, starts: e.target.value }))} />
            </label>
            <label className="calField">
              <span className="calFieldLabel">To</span>
              <input type="month" className="calInput" value={form.ends} required
                onChange={(e) => setForm((was) => ({ ...was, ends: e.target.value }))} />
            </label>
          </div>
          {error && <p className="calError">{error}</p>}
          <div className="calFormActions">
            {editing && <button type="button" className="calButton" onClick={reset} disabled={busy}>Cancel edit</button>}
            <button type="button" className="calButton" onClick={onClose} disabled={busy}>Close</button>
            <button type="submit" className="calButton calButtonPrimary" disabled={busy}>
              {editing ? "Save season" : "Add season"}
            </button>
          </div>
        </form>
      </Modal>

      <DeleteConfirmModal
        open={removing !== null}
        title="Delete this season?"
        message={removing ? `"${removing.name}" will be deleted. No application is deleted with it.` : ""}
        confirmLabel="Delete the season"
        submitting={busy}
        error={error}
        onCancel={() => setRemoving(null)}
        onConfirm={async () => {
          const target = removing;
          setRemoving(null);
          if (!user || !target) return;
          try {
            await deleteSeason(user.id, target.id);
            if (editing?.id === target.id) reset();
            onSaved();
          } catch (err) {
            setError(err instanceof Error ? err.message : "Could not delete the season");
          }
        }}
      />
    </>
  );
}
