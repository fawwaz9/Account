import { useEffect, useState } from "react";
import Modal from "../../../shared/components/Modal";
import { setTaskDone, updateTask } from "../api";
import {
  MAX_PRIORITY,
  MIN_PRIORITY,
  PRIORITY_LABELS,
  Task,
  TaskUpdate,
} from "../types";
import { numberOrNull, parseTags, tagText, withDueDate } from "../taskFields";
import { Course } from "../../grades/types";
import { useAuth } from "../../../app/auth/AuthContext";

/** 1..5, for the select. */
const PRIORITY_STEPS = Array.from(
  { length: MAX_PRIORITY - MIN_PRIORITY + 1 },
  (_, index) => MIN_PRIORITY + index
);

interface EditTaskModalProps {
  readonly task: Task | null;
  readonly courses: Course[];
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

interface FormState {
  title: string;
  notes: string | null;
  due_date: string | null;
  due_time: string | null;
  estimated_minutes: number | null;
  course_id: string | null;
  priority: number;
}

function formFor(task: Task): FormState {
  return {
    title: task.title,
    notes: task.notes,
    due_date: task.due_date,
    // The API sends HH:MM:SS and <input type="time"> wants HH:MM, showing
    // nothing at all when handed anything longer.
    due_time: task.due_time ? task.due_time.slice(0, 5) : null,
    estimated_minutes: task.estimated_minutes,
    course_id: task.course_id,
    priority: task.priority,
  };
}

/**
 * Editing one task.
 *
 * The only way to change a task after it is created -- before this, a title
 * typed wrongly or a deadline that moved could be deleted and retyped, and
 * nothing else. Opened from a row on the task page and from a task on the
 * calendar, deliberately the same dialog: two editors for one record is how
 * the two end up offering different fields.
 *
 * Completing lives here too, and is a button rather than a checkbox in the
 * field list because it is the one control that changes something without
 * being a save. It sits apart from Cancel and Save for the same reason.
 */
export default function EditTaskModal({
  task,
  courses,
  onClose,
  onSaved,
}: EditTaskModalProps) {
  const { user } = useAuth();
  const [form, setForm] = useState<FormState | null>(task ? formFor(task) : null);
  const [tags, setTags] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setForm(task ? formFor(task) : null);
    setTags(task ? tagText(task.tags) : "");
    setError(null);
  }, [task]);

  if (!task || !form) return null;

  // The gradebook rewrites these two on every grade save, so offering them here
  // would be offering an edit that silently reverts. Everything else is left
  // alone by `sync_task` and is genuinely the student's.
  const fromGrade = task.grade_id !== null;

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => (current ? { ...current, [key]: value } : current));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user || !task || !form) return;

    setSaving(true);
    setError(null);
    try {
      const payload: TaskUpdate = {
        title: form.title.trim(),
        notes: form.notes?.trim() || null,
        due_date: form.due_date,
        due_time: form.due_time,
        estimated_minutes: form.estimated_minutes,
        course_id: form.course_id,
        priority: form.priority,
        tags: parseTags(tags),
      };
      await updateTask(user.id, task.id, payload);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save that");
    } finally {
      setSaving(false);
    }
  }

  async function handleDone() {
    if (!user || !task) return;

    setSaving(true);
    setError(null);
    try {
      // Whatever is typed above is deliberately not saved first. Ticking a task
      // off is one decision and editing it is another, and a Complete button
      // that quietly also saved a half-finished edit would be two.
      await setTaskDone(user.id, task.id, !task.done);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update that");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title={`Edit · ${task.title}`} onClose={onClose}>
      <form className="calForm" onSubmit={handleSubmit}>
        {/* Said before the fields rather than after a failed save. An
            occurrence is an ordinary row in every other respect, so nothing
            else on screen would tell you a repeat is maintaining it. */}
        {task.recurring_id && (
          <p className="small-text muted">
            One of a repeat. Changes here apply to this day only — editing the
            repeat itself will write over them.
          </p>
        )}

        {fromGrade && (
          <p className="small-text muted">
            Raised from a grade, so its name and deadline follow the gradebook
            and are changed on the course page. Everything else here is yours.
          </p>
        )}

        <label className="calField">
          <span className="calFieldLabel">Title</span>
          <input
            id="edit-task-title"
            className="calInput"
            value={form.title}
            onChange={(event) => update("title", event.target.value)}
            disabled={fromGrade}
            required
          />
        </label>

        <label className="calField">
          <span className="calFieldLabel">Course</span>
          <select
            id="edit-task-course"
            className="calInput"
            value={form.course_id ?? ""}
            onChange={(event) => update("course_id", event.target.value || null)}
            disabled={fromGrade}
          >
            <option value="">No course</option>
            {courses.map((course) => (
              <option key={course.id} value={course.id}>{course.code}</option>
            ))}
          </select>
        </label>

        <div className="taskEditRow">
          <label className="calField">
            <span className="calFieldLabel">Due</span>
            <input
              id="edit-task-due"
              type="date"
              className="calInput"
              value={form.due_date ?? ""}
              onChange={(event) =>
                setForm((current) =>
                  current ? withDueDate(current, event.target.value || null) : current
                )
              }
              disabled={fromGrade}
            />
          </label>

          {/* Only once there is a date to attach it to. A time on its own is
              not a deadline, and the API refuses one. */}
          {form.due_date && (
            <label className="calField">
              <span className="calFieldLabel">At</span>
              <input
                id="edit-task-due-time"
                type="time"
                className="calInput"
                value={form.due_time ?? ""}
                onChange={(event) => update("due_time", event.target.value || null)}
                disabled={fromGrade}
              />
            </label>
          )}
        </div>

        <div className="taskEditRow">
          <label className="calField">
            <span className="calFieldLabel">Priority</span>
            <select
              id="edit-task-priority"
              className="calInput"
              value={form.priority}
              onChange={(event) => update("priority", Number(event.target.value))}
            >
              {PRIORITY_STEPS.map((step) => (
                <option key={step} value={step}>{step} · {PRIORITY_LABELS[step]}</option>
              ))}
            </select>
          </label>

          <label className="calField">
            <span className="calFieldLabel">Estimate</span>
            <input
              id="edit-task-estimate"
              type="number"
              min={1}
              max={2400}
              className="calInput"
              value={form.estimated_minutes ?? ""}
              onChange={(event) =>
                update("estimated_minutes", numberOrNull(event.target.value))
              }
              placeholder="mins"
            />
          </label>
        </div>

        <label className="calField">
          <span className="calFieldLabel">Tags</span>
          <input
            id="edit-task-tags"
            className="calInput"
            value={tags}
            onChange={(event) => setTags(event.target.value)}
            placeholder="tags, comma separated"
          />
        </label>

        <label className="calField">
          <span className="calFieldLabel">Notes</span>
          <textarea
            id="edit-task-notes"
            className="calInput"
            rows={3}
            value={form.notes ?? ""}
            onChange={(event) => update("notes", event.target.value || null)}
          />
        </label>

        {error && <p className="calError">{error}</p>}

        <div className="taskEditActions">
          {/* Away from Save, because it is not one: a student reaching for
              "done" should not be able to hit it on the way past. */}
          <button
            type="button"
            className="calButton"
            onClick={handleDone}
            disabled={saving}
          >
            {task.done ? "Reopen" : "Mark complete"}
          </button>

          <div className="calFormActions">
            <button type="button" className="calButton" onClick={onClose} disabled={saving}>
              Cancel
            </button>
            <button type="submit" className="calButton calButtonPrimary" disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  );
}
