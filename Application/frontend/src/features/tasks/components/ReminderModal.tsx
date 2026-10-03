import { useEffect, useState } from "react";
import Modal from "../../../shared/components/Modal";
import HelpTip from "../../../shared/components/HelpTip";
import DeleteConfirmModal from "../../grades/components/DeleteConfirmModal";
import { createReminder, deleteReminder, fetchReminders } from "../api";
import { requestNotificationPermission } from "../hooks/useReminders";
import { Reminder, ReminderCreate } from "../types";
import { Course } from "../../grades/types";
import { useAuth } from "../../../app/auth/AuthContext";
import { addDays, clockTime, dueLabel, today } from "../../../shared/utils/dateUtils";

interface ReminderModalProps {
  readonly open: boolean;
  readonly courses: Course[];
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

function blank(): ReminderCreate {
  return {
    title: "",
    notes: null,
    // Tomorrow morning: a reminder set for a time already gone would fire the
    // moment it was saved, which is nobody's intention.
    remind_at: `${addDays(today(), 1)}T09:00`,
    course_id: null,
  };
}

/**
 * Making a reminder, and the one moment it makes sense to ask for permission.
 *
 * The browser is asked on the first save, never on page load: a prompt with no
 * context is the one people dismiss forever, and there is no second chance to
 * ask. Declining costs nothing here — the in-app banner is the reliable path
 * either way.
 */
export default function ReminderModal({ open, courses, onClose, onSaved }: ReminderModalProps) {
  const { user } = useAuth();
  const [form, setForm] = useState<ReminderCreate>(blank());
  const [pending, setPending] = useState<Reminder[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Deleting a reminder is permanent; there is no archive and no restore.
  const [deleting, setDeleting] = useState<Reminder | null>(null);

  useEffect(() => {
    if (!open || !user) return;

    setForm(blank());
    setError(null);

    let cancelled = false;
    fetchReminders(user.id)
      .then((rows) => { if (!cancelled) setPending(rows); })
      .catch(() => { if (!cancelled) setPending([]); });

    return () => { cancelled = true; };
  }, [open, user]);

  if (!open) return null;

  function update<K extends keyof ReminderCreate>(key: K, value: ReminderCreate[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;

    setSaving(true);
    setError(null);
    try {
      await createReminder(user.id, { ...form, title: form.title.trim() });
      // Asked after the save, so a denied prompt cannot lose the reminder.
      await requestNotificationPermission();
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save that reminder");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(reminder: Reminder) {
    setDeleting(null);
    if (!user) return;
    setPending((current) => current.filter((row) => row.id !== reminder.id));
    try {
      await deleteReminder(user.id, reminder.id);
      onSaved();
    } catch {
      setError("Could not remove that one");
    }
  }

  return (
    <Modal title="Reminders" onClose={onClose}>
      <form className="calForm" onSubmit={handleSubmit}>
        <HelpTip label="What a reminder is">
          A reminder notifies rather than waits — there is nothing to tick off. It
          only fires while the app is open, so it is a nudge while you are using the
          app rather than a notification that will reach you otherwise.
        </HelpTip>

        <label className="calField">
          <span className="calFieldLabel">Remind me to</span>
          <input
            className="calInput"
            value={form.title}
            onChange={(event) => update("title", event.target.value)}
            placeholder="Email Dr Hale about the extension"
            required
          />
        </label>

        <div className="calRow">
          <label className="calField">
            <span className="calFieldLabel">When</span>
            <input
              type="datetime-local"
              className="calInput"
              value={form.remind_at}
              onChange={(event) => update("remind_at", event.target.value)}
              required
            />
          </label>

          <label className="calField">
            <span className="calFieldLabel">Course</span>
            <select
              className="calInput"
              value={form.course_id ?? ""}
              onChange={(event) => update("course_id", event.target.value || null)}
            >
              <option value="">No course</option>
              {courses.map((course) => (
                <option key={course.id} value={course.id}>{course.code}</option>
              ))}
            </select>
          </label>
        </div>

        {error && <p className="calError">{error}</p>}

        <div className="calFormActions">
          <button type="button" className="calButton" onClick={onClose} disabled={saving}>
            Close
          </button>
          <button type="submit" className="calButton calButtonPrimary" disabled={saving}>
            {saving ? "Saving…" : "Add reminder"}
          </button>
        </div>
      </form>

      {pending.length > 0 && (
        <div className="remPending">
          <span className="small-text muted">Coming up</span>
          <ul>
            {pending.map((reminder) => (
              <li key={reminder.id}>
                <span className="small-text">
                  {reminder.title}
                  <span className="muted">
                    {" · "}
                    {dueLabel(reminder.remind_at.slice(0, 10))}{" "}
                    {clockTime(reminder.remind_at.slice(11, 16))}
                  </span>
                </span>
                <button
                  type="button"
                  className="calButton calButtonDanger"
                  onClick={() => setDeleting(reminder)}
                  aria-label={`Remove ${reminder.title}`}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <DeleteConfirmModal
        open={deleting !== null}
        title="Delete this reminder?"
        message={
          deleting
            ? `"${deleting.title}" will be deleted. Reminders have no archive, so ` +
              `this cannot be undone.`
            : ""
        }
        submitting={false}
        error={error}
        onCancel={() => setDeleting(null)}
        onConfirm={() => { if (deleting) void handleDelete(deleting); }}
      />
    </Modal>
  );
}
