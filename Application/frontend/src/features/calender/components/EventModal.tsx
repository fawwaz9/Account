import { useEffect, useState } from "react";
import Modal from "../../../shared/components/Modal";
import RecurrenceEditor from "./RecurrenceEditor";
import { createEvent, updateEvent } from "../api";
import {
  CalendarEvent,
  EVENT_KIND_LABELS,
  EventCreate,
  EventKind,
} from "../types";
import { Course } from "../../grades/types";
import { useAuth } from "../../../app/auth/AuthContext";

interface EventModalProps {
  readonly open: boolean;
  /** The event being edited, or null to add a new one. */
  readonly event: CalendarEvent | null;
  /** Pre-fills the date when the student clicked an empty day. */
  readonly defaultDate: string;
  readonly courses: Course[];
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

function blankEvent(date: string): EventCreate {
  return {
    title: "",
    kind: "personal",
    course_id: null,
    location: null,
    notes: null,
    starts_on: date,
    start_time: null,
    end_time: null,
    recurrence: null,
  };
}

function formFor(event: CalendarEvent | null, date: string): EventCreate {
  if (!event) return blankEvent(date);

  return {
    title: event.title,
    kind: event.kind,
    course_id: event.course_id,
    location: event.location,
    notes: event.notes,
    starts_on: event.starts_on,
    // The API sends HH:MM:SS; <input type="time"> wants HH:MM and silently
    // shows nothing when handed anything longer.
    start_time: event.start_time ? event.start_time.slice(0, 5) : null,
    end_time: event.end_time ? event.end_time.slice(0, 5) : null,
    recurrence: event.recurrence,
  };
}

export default function EventModal({
  open,
  event,
  defaultDate,
  courses,
  onClose,
  onSaved,
}: EventModalProps) {
  const { user } = useAuth();
  const [form, setForm] = useState<EventCreate>(formFor(event, defaultDate));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setForm(formFor(event, defaultDate));
    setError(null);
  }, [event, defaultDate, open]);

  if (!open) return null;

  function update<K extends keyof EventCreate>(key: K, value: EventCreate[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmit(submitEvent: React.FormEvent) {
    submitEvent.preventDefault();
    if (!user) return;

    setSaving(true);
    setError(null);
    try {
      if (event) {
        await updateEvent(user.id, event.id, form);
      } else {
        await createEvent(user.id, form);
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the event");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      title={event ? "Edit event" : "New event"}
      onClose={onClose}
      panelClassName="widePopup"
    >
      <form className="calForm" onSubmit={handleSubmit}>
        <label className="calField">
          <span className="calFieldLabel">Title</span>
          <input
            className="calInput"
            value={form.title}
            onChange={(changed) => update("title", changed.target.value)}
            placeholder="Midterm, gym, rent"
            required
          />
        </label>

        <div className="calRow">
          <label className="calField">
            <span className="calFieldLabel">Kind</span>
            <select
              className="calInput"
              value={form.kind}
              onChange={(changed) => update("kind", changed.target.value as EventKind)}
            >
              {Object.entries(EVENT_KIND_LABELS).map(([kind, label]) => (
                <option key={kind} value={kind}>{label}</option>
              ))}
            </select>
          </label>

          <label className="calField">
            <span className="calFieldLabel">Course</span>
            <select
              className="calInput"
              value={form.course_id ?? ""}
              onChange={(changed) => update("course_id", changed.target.value || null)}
            >
              <option value="">None</option>
              {courses.map((course) => (
                <option key={course.id} value={course.id}>{course.code}</option>
              ))}
            </select>
          </label>
        </div>

        <div className="calRow">
          <label className="calField">
            <span className="calFieldLabel">Date</span>
            <input
              type="date"
              className="calInput"
              value={form.starts_on}
              onChange={(changed) => update("starts_on", changed.target.value)}
              required
            />
          </label>

          <label className="calField">
            <span className="calFieldLabel">From</span>
            <input
              type="time"
              className="calInput"
              value={form.start_time ?? ""}
              onChange={(changed) => update("start_time", changed.target.value || null)}
            />
          </label>

          <label className="calField">
            <span className="calFieldLabel">To</span>
            <input
              type="time"
              className="calInput"
              value={form.end_time ?? ""}
              onChange={(changed) => update("end_time", changed.target.value || null)}
            />
          </label>
        </div>
        <p className="calHint">Leave the times blank for an all-day event.</p>

        <RecurrenceEditor
          value={form.recurrence}
          onChange={(recurrence) => update("recurrence", recurrence)}
          startsOn={form.starts_on}
        />

        <label className="calField">
          <span className="calFieldLabel">Location</span>
          <input
            className="calInput"
            value={form.location ?? ""}
            onChange={(changed) => update("location", changed.target.value || null)}
            placeholder="SWNG 222"
          />
        </label>

        <label className="calField">
          <span className="calFieldLabel">Notes</span>
          <textarea
            className="calInput"
            rows={2}
            value={form.notes ?? ""}
            onChange={(changed) => update("notes", changed.target.value || null)}
          />
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
