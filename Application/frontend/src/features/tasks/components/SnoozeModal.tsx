import { useEffect, useState } from "react";
import Modal from "../../../shared/components/Modal";
import HelpTip from "../../../shared/components/HelpTip";
import { fetchSnoozes, snoozeTask } from "../api";
import { Task, TaskSnooze } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";
import { addDays, dueLabel, today } from "../../../shared/utils/dateUtils";

/** The task to snooze (null when closed), and the close and saved callbacks. */
interface SnoozeModalProps {
  readonly task: Task | null;
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

/** Quick choices for how long to snooze, in days. */
const PRESETS = [
  { label: "Tomorrow", days: 1 },
  { label: "In three days", days: 3 },
  { label: "Next week", days: 7 },
];

/**
 * Snooze a task until a date, with a reason; the due date never moves.
 * Earlier snoozes and their reasons are listed, so a task blocked on one thing says so.
 */
export default function SnoozeModal({ task, onClose, onSaved }: SnoozeModalProps) {
  const { user } = useAuth();
  const [until, setUntil] = useState(addDays(today(), 1));
  const [reason, setReason] = useState("");
  const [history, setHistory] = useState<TaskSnooze[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setUntil(addDays(today(), 1));
    setReason("");
    setError(null);
    setHistory([]);

    if (!user || !task || task.snooze_count === 0) return;

    let cancelled = false;
    fetchSnoozes(user.id, task.id)
      .then((rows) => { if (!cancelled) setHistory(rows); })
      .catch(() => { if (!cancelled) setHistory([]); });

    return () => { cancelled = true; };
  }, [user, task]);

  if (!task) return null;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user || !task) return;

    setSaving(true);
    setError(null);
    try {
      await snoozeTask(user.id, task.id, { until, reason: reason.trim() || null });
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not snooze that");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title={`Snooze · ${task.title}`} onClose={onClose}>
      <form className="calForm" onSubmit={handleSubmit}>
        <HelpTip label="What snoozing does">
          It leaves the list until the date you pick and comes back in its own place.
          The due date{task.due_date ? ` of ${dueLabel(task.due_date)}` : ""} does not
          move, so nothing about when the work is actually owed changes.
        </HelpTip>

        <div className="snoozePresets">
          {PRESETS.map((preset) => {
            const date = addDays(today(), preset.days);
            return (
              <button
                key={preset.label}
                type="button"
                className={until === date ? "snoozePreset snoozePresetOn" : "snoozePreset"}
                onClick={() => setUntil(date)}
                aria-pressed={until === date}
              >
                {preset.label}
              </button>
            );
          })}
        </div>

        <label className="calField">
          <span className="calFieldLabel">Until</span>
          <input
            type="date"
            className="calInput"
            value={until}
            min={addDays(today(), 1)}
            onChange={(event) => setUntil(event.target.value)}
            required
          />
        </label>

        <label className="calField">
          <span className="calFieldLabel">Why</span>
          <input
            className="calInput"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Waiting on my lab partner"
          />
        </label>

        {/* Shown here because this is where it changes a decision: the fourth
            time you push something back for the same reason, the reason is the
            problem rather than the task. */}
        {history.length > 0 && (
          <div className="snoozeHistory">
            <span className="small-text muted">
              Pushed back {history.length} {history.length === 1 ? "time" : "times"} already
            </span>
            <ul>
              {history.map((entry) => (
                <li key={entry.id}>
                  <span className="small-text muted">{entry.snoozed_at.slice(0, 10)}</span>
                  <span className="small-text">{entry.reason ?? "no reason given"}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {error && <p className="calError">{error}</p>}

        <div className="calFormActions">
          <button type="button" className="calButton" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className="calButton calButtonPrimary" disabled={saving}>
            {saving ? "Saving…" : "Snooze"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
