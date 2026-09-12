import { useEffect, useState } from "react";
import { createBlackout, deleteBlackout, fetchBlackouts } from "../api";
import { TermBlackout } from "../types";
import { getErrorMessage } from "../../grades/components/AddCourseModal";
import { useAuth } from "../../../app/auth/AuthContext";
import { fromIso, today } from "../../../shared/utils/dateUtils";
import Modal from "../../../shared/components/Modal";

interface BlackoutsModalProps {
  readonly open: boolean;
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

/**
 * Weeks of term when classes do not run.
 *
 * Entered once and subtracted from every class, because one reading break
 * applies to all six courses and entering it on each of them is how one ends up
 * wrong.
 *
 * A range rather than a list of dates: a reading break is a week and a stat
 * holiday is a range of one, so one row covers both.
 */
export default function BlackoutsModal({ open, onClose, onSaved }: BlackoutsModalProps) {
  const { user } = useAuth();
  const [rows, setRows] = useState<TermBlackout[]>([]);
  const [label, setLabel] = useState("");
  const [startsOn, setStartsOn] = useState(today());
  const [endsOn, setEndsOn] = useState(today());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !user) return;
    let cancelled = false;
    fetchBlackouts(user.id)
      .then((found) => { if (!cancelled) setRows(found); })
      .catch(() => { if (!cancelled) setRows([]); });
    return () => { cancelled = true; };
  }, [open, user]);

  async function reload() {
    if (!user) return;
    setRows(await fetchBlackouts(user.id));
    // The calendar behind this is now showing classes that no longer run.
    onSaved();
  }

  async function handleAdd(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;
    setBusy(true);
    setError(null);
    try {
      await createBlackout(user.id, {
        label: label.trim(),
        starts_on: startsOn,
        // A single day is a range of one, so the end defaults to the start
        // rather than making you enter the same date twice.
        ends_on: endsOn < startsOn ? startsOn : endsOn,
      });
      setLabel("");
      await reload();
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(id: string) {
    if (!user) return;
    setBusy(true);
    setError(null);
    try {
      await deleteBlackout(user.id, id);
      await reload();
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  function span(row: TermBlackout) {
    const from = fromIso(row.starts_on).toLocaleDateString(undefined, {
      day: "numeric", month: "short",
    });
    if (row.days === 1) return from;
    const to = fromIso(row.ends_on).toLocaleDateString(undefined, {
      day: "numeric", month: "short",
    });
    return `${from} – ${to}`;
  }

  return (
    <Modal title="Blocked periods" onClose={onClose} panelClassName="widePopup">
      <p className="blackoutIntro">
        Weeks when classes do not run. Applied to everything attached to a course
        — your own events, standing payments and repeating tasks carry on.
      </p>

      {rows.length > 0 && (
        <ul className="blackoutList">
          {rows.map((row) => (
            <li key={row.id}>
              <span className="blackoutLabel">{row.label}</span>
              <span className="blackoutSpan">{span(row)}</span>
              <span className="blackoutDays">
                {row.days} {row.days === 1 ? "day" : "days"}
              </span>
              <button
                type="button"
                className="bulkRemove"
                onClick={() => handleDelete(row.id)}
                disabled={busy}
                aria-label={`Remove ${row.label}`}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <form className="loginForm" onSubmit={handleAdd}>
        <div className="calRow">
          <div className="loginField calField">
            <label htmlFor="blackout-label">What is it</label>
            <input
              id="blackout-label"
              className="loginInput"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              placeholder="e.g. Reading break"
              required
            />
          </div>
          <div className="loginField calField">
            <label htmlFor="blackout-start">From</label>
            <input
              id="blackout-start"
              className="loginInput"
              type="date"
              value={startsOn}
              onChange={(event) => {
                setStartsOn(event.target.value);
                // Keeps a single day as a single day without a second entry.
                if (endsOn < event.target.value) setEndsOn(event.target.value);
              }}
              required
            />
          </div>
          <div className="loginField calField">
            <label htmlFor="blackout-end">To</label>
            <input
              id="blackout-end"
              className="loginInput"
              type="date"
              min={startsOn}
              value={endsOn}
              onChange={(event) => setEndsOn(event.target.value)}
              required
            />
          </div>
        </div>

        {error && <p className="error">{error}</p>}

        <div className="calActions">
          <button type="button" className="buttons" onClick={onClose}>Done</button>
          <button type="submit" className="buttons !bg-gold" disabled={busy || !label.trim()}>
            {busy ? "Saving…" : "Block this period"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
