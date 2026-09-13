import { useEffect, useState } from "react";
import Modal from "../../../shared/components/Modal";
import { fetchSnoozes, snoozeTask } from "../api";
import { Task, TaskSnooze } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";
import { addDays, dueLabel, today } from "../../../shared/utils/dateUtils";

interface SnoozeModalProps {
  readonly task: Task | null;
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

/** The three answers to "until when" that cover almost every case. */
const PRESETS = [
  { label: "Tomorrow", days: 1 },
  { label: "In three days", days: 3 },
  { label: "Next week", days: 7 },
];

/**
 * Pushing a task back, and saying why.
 *
 * The reason is the feature rather than a nicety. A task snoozed three times
 * citing the same thing is blocked on that thing, and nothing else in the app
 * would ever say so — which is why every snooze is kept rather than the latest
 * overwriting the one before.
 *
 * The due date is not offered as something to change here. It does not move,
 * and the past snoozes are shown so the deferral is visible rather than
 * disguised as a later deadline.
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
        <p className="small-text muted">
          It leaves the list until then and comes back in its own place. The due
          date{task.due_date ? ` of ${dueLabel(task.due_date)}` : ""} does not move.
        </p>

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
