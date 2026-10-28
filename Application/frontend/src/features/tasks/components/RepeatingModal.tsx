import { useEffect, useState } from "react";
import Modal from "../../../shared/components/Modal";
import RecurrenceEditor from "../../calender/components/RecurrenceEditor";
import { createRepeating, updateRepeating } from "../api";
import {
  DEFAULT_PRIORITY,
  MAX_PRIORITY,
  MIN_PRIORITY,
  PRIORITY_LABELS,
  RecurringTask,
  RecurringTaskCreate,
} from "../types";

/** Every priority step, lowest first, for the select. */
const PRIORITY_STEPS = Array.from(
  { length: MAX_PRIORITY - MIN_PRIORITY + 1 },
  (_, index) => MIN_PRIORITY + index
);
import { Course } from "../../grades/types";
import { useAuth } from "../../../app/auth/AuthContext";
import { today, weekdayCode } from "../../../shared/utils/dateUtils";

/** Whether the dialog is open, the rule to edit, the courses, and the close and saved callbacks. */
interface RepeatingModalProps {
  readonly open: boolean;
  /** The repeat being edited, or null to set up a new one. */
  readonly rule: RecurringTask | null;
  readonly courses: Course[];
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

/** A new repeat starting today, weekly on today's weekday, at the default priority. */
function blankRule(): RecurringTaskCreate {
  const start = today();

  return {
    title: "",
    notes: null,
    due_time: null,
    estimated_minutes: null,
    course_id: null,
    tags: [],
    priority: DEFAULT_PRIORITY,
    starts_on: start,
    // Weekly on today's weekday: the commonest repeating chore by far, and
    // showing the day already chosen makes the rule legible at a glance.
    recurrence: { freq: "weekly", interval: 1, byday: [weekdayCode(start)], until: null, count: null },
    active: true,
  };
}

/** Form state for a repeating task, or a blank one; its time is cut to "HH:MM". */
function formFor(rule: RecurringTask | null): RecurringTaskCreate {
  if (!rule) return blankRule();

  return {
    title: rule.title,
    notes: rule.notes,
    // The API sends HH:MM:SS; <input type="time"> shows nothing for anything longer.
    due_time: rule.due_time ? rule.due_time.slice(0, 5) : null,
    estimated_minutes: rule.estimated_minutes,
    course_id: rule.course_id,
    tags: rule.tags,
    priority: rule.priority,
    starts_on: rule.starts_on,
    recurrence: rule.recurrence,
    active: rule.active,
  };
}

/** Add or edit a repeating task's template and rule; the rule always keeps a frequency. */
export default function RepeatingModal({
  open,
  rule,
  courses,
  onClose,
  onSaved,
}: RepeatingModalProps) {
  const { user } = useAuth();
  const [form, setForm] = useState<RecurringTaskCreate>(formFor(rule));
  const [tagText, setTagText] = useState(rule?.tags.join(", ") ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setForm(formFor(rule));
    setTagText(rule?.tags.join(", ") ?? "");
    setError(null);
  }, [rule, open]);

  if (!open) return null;

  function update<K extends keyof RecurringTaskCreate>(key: K, value: RecurringTaskCreate[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;

    const payload: RecurringTaskCreate = {
      ...form,
      title: form.title.trim(),
      tags: tagText.split(",").map((tag) => tag.trim()).filter(Boolean),
    };

    setSaving(true);
    setError(null);
    try {
      if (rule) {
        await updateRepeating(user.id, rule.id, payload);
      } else {
        await createRepeating(user.id, payload);
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save this");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      title={rule ? "Edit repeating task" : "New repeating task"}
      onClose={onClose}
      panelClassName="widePopup"
    >
      <form className="calForm" onSubmit={handleSubmit}>
        <label className="calField">
          <span className="calFieldLabel">Task</span>
          <input
            className="calInput"
            value={form.title}
            onChange={(event) => update("title", event.target.value)}
            placeholder="Readings, lab prep, laundry"
            required
          />
        </label>

        <div className="calRow">
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

          <label className="calField">
            <span className="calFieldLabel">Minutes each</span>
            <input
              type="number"
              min={1}
              max={2400}
              className="calInput"
              // Number("") is 0, which would mean "takes no time" rather than
              // "no estimate given".
              value={form.estimated_minutes ?? ""}
              onChange={(event) =>
                update(
                  "estimated_minutes",
                  event.target.value === "" ? null : Number(event.target.value)
                )
              }
              placeholder="90"
            />
          </label>

          <label className="calField">
            <span className="calFieldLabel">Due at</span>
            <input
              type="time"
              className="calInput"
              value={form.due_time ?? ""}
              onChange={(event) => update("due_time", event.target.value || null)}
            />
          </label>

          <label className="calField">
            <span className="calFieldLabel">Priority</span>
            {/* On the rule, not on each occurrence: a chore that repeats sixty
                times would otherwise need correcting sixty times. */}
            <select
              className="calInput"
              value={form.priority}
              onChange={(event) => update("priority", Number(event.target.value))}
            >
              {PRIORITY_STEPS.map((step) => (
                <option key={step} value={step}>{step} · {PRIORITY_LABELS[step]}</option>
              ))}
            </select>
          </label>
        </div>

        <label className="calField">
          <span className="calFieldLabel">First one on</span>
          <input
            type="date"
            className="calInput"
            value={form.starts_on}
            onChange={(event) => update("starts_on", event.target.value)}
            required
          />
        </label>

        <RecurrenceEditor
          value={form.recurrence}
          onChange={(recurrence) =>
            // A task that does not repeat is just a task, so the rule always
            // keeps a frequency; clearing it falls back to weekly.
            update("recurrence", recurrence ?? {
              freq: "weekly", interval: 1, byday: [weekdayCode(form.starts_on)],
              until: null, count: null,
            })
          }
          startsOn={form.starts_on}
        />

        <label className="calField">
          <span className="calFieldLabel">Tags</span>
          <input
            className="calInput"
            value={tagText}
            onChange={(event) => setTagText(event.target.value)}
            placeholder="comma separated"
          />
        </label>

        <label className="calField">
          <span className="calFieldLabel">Notes</span>
          <textarea
            className="calInput"
            rows={2}
            value={form.notes ?? ""}
            onChange={(event) => update("notes", event.target.value || null)}
          />
        </label>

        <label className="taskToggle">
          <input
            type="checkbox"
            checked={form.active}
            onChange={(event) => update("active", event.target.checked)}
          />
          Active — uncheck to stop new ones without losing what is done
        </label>

        {error && <p className="calError">{error}</p>}

        <div className="calFormActions">
          <button type="button" className="calButton" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className="calButton calButtonPrimary" disabled={saving}>
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
