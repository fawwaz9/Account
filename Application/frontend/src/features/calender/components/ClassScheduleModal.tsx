import { useEffect, useState } from "react";
import Modal from "../../../shared/components/Modal";
import { fetchClassSchedule, setClassSchedule } from "../api";
import {
  CLASS_KINDS,
  CalendarEvent,
  ClassMeeting,
  EVENT_KIND_LABELS,
  EventKind,
  INTERVAL_LABELS,
  MAX_MEETING_INTERVAL,
  Weekday,
} from "../types";
import { useAuth } from "../../../app/auth/AuthContext";
import { WEEKDAY_CODES } from "../../../shared/utils/dateUtils";

const DAY_INITIALS: Record<Weekday, string> = {
  MO: "M", TU: "T", WE: "W", TH: "T", FR: "F", SA: "S", SU: "S",
};

const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

interface ClassScheduleModalProps {
  readonly open: boolean;
  readonly courseId: string;
  readonly courseCode: string;
  /** Used only to say which dates the timetable will run between. */
  readonly startDate: string | null;
  readonly endDate: string | null;
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

function blankMeeting(): ClassMeeting {
  return {
    kind: "lecture", days: [], start_time: "09:00", end_time: "10:00",
    location: null, interval: 1, first_on: null,
  };
}

/** The stored events back into the rows the form edits. */
function meetingsFrom(events: CalendarEvent[]): ClassMeeting[] {
  return events.map((event) => ({
    kind: event.kind,
    days: event.recurrence?.byday ?? [],
    // The API sends HH:MM:SS; <input type="time"> shows nothing for anything longer.
    start_time: (event.start_time ?? "09:00").slice(0, 5),
    end_time: (event.end_time ?? "10:00").slice(0, 5),
    location: event.location,
    interval: event.recurrence?.interval ?? 1,
    // The event's own start date *is* the phase for anything not weekly, which
    // is why reopening the form shows the week the cycle really starts on
    // rather than resetting it to the term start.
    first_on: (event.recurrence?.interval ?? 1) > 1 ? event.starts_on : null,
  }));
}

/**
 * A course's class times, as a timetable rather than as events.
 *
 * Each row becomes one weekly repeat bounded by the course's own term dates, so
 * a term of lectures is three rows of form and three rows in the database. The
 * whole timetable is replaced on save: fixing a room must not leave the old room
 * on the calendar beside the new one.
 */
export default function ClassScheduleModal({
  open,
  courseId,
  courseCode,
  startDate,
  endDate,
  onClose,
  onSaved,
}: ClassScheduleModalProps) {
  const { user } = useAuth();
  const [meetings, setMeetings] = useState<ClassMeeting[]>([blankMeeting()]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load what is already on the calendar, so opening this is an edit rather
  // than a blank form that silently discards the existing timetable on save.
  useEffect(() => {
    if (!open || !user) return;

    let mounted = true;
    setLoading(true);
    setError(null);

    fetchClassSchedule(user.id, courseId)
      .then((events) => {
        if (!mounted) return;
        const existing = meetingsFrom(events);
        setMeetings(existing.length ? existing : [blankMeeting()]);
      })
      .catch((err) => {
        if (mounted) setError(err instanceof Error ? err.message : "Could not load the timetable");
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => { mounted = false; };
  }, [open, user, courseId]);

  if (!open) return null;

  function updateMeeting(index: number, patch: Partial<ClassMeeting>) {
    setMeetings((current) =>
      current.map((meeting, at) => (at === index ? { ...meeting, ...patch } : meeting))
    );
  }

  function toggleDay(index: number, day: Weekday) {
    const meeting = meetings[index];
    updateMeeting(index, {
      days: meeting.days.includes(day)
        ? meeting.days.filter((code) => code !== day)
        : [...meeting.days, day],
    });
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;

    // A row with no days selected is an unused slot, not an error -- the same
    // rule the bulk grade form follows for a blank row.
    const filled = meetings.filter((meeting) => meeting.days.length > 0);

    setSaving(true);
    setError(null);
    try {
      await setClassSchedule(user.id, courseId, {
        meetings: filled,
        starts_on: null,
        ends_on: null,
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the timetable");
    } finally {
      setSaving(false);
    }
  }

  const hasTermDates = Boolean(startDate && endDate);

  return (
    <Modal title={`${courseCode} class times`} onClose={onClose} panelClassName="widePopup">
      <form className="calForm" onSubmit={handleSubmit}>
        {hasTermDates ? (
          <p className="calHint">
            Repeats weekly from {startDate} to {endDate}, taken from the course.
          </p>
        ) : (
          <p className="calError">
            This course has no start and end date. Add them on the course first,
            or the timetable has no term to run in.
          </p>
        )}

        {loading && <p className="calMuted" role="status">Loading…</p>}

        {meetings.map((meeting, index) => (
          <fieldset key={index} className="calRecurrence">
            <legend className="calFieldLabel">Meeting {index + 1}</legend>

            <div className="calRow">
              <label className="calField">
                <span className="calFieldLabel">Kind</span>
                <select
                  className="calInput"
                  value={meeting.kind}
                  onChange={(event) =>
                    updateMeeting(index, { kind: event.target.value as EventKind })
                  }
                >
                  {CLASS_KINDS.map((kind) => (
                    <option key={kind} value={kind}>{EVENT_KIND_LABELS[kind]}</option>
                  ))}
                </select>
              </label>

              <label className="calField">
                <span className="calFieldLabel">From</span>
                <input
                  type="time"
                  className="calInput"
                  value={meeting.start_time}
                  onChange={(event) => updateMeeting(index, { start_time: event.target.value })}
                  required
                />
              </label>

              <label className="calField">
                <span className="calFieldLabel">To</span>
                <input
                  type="time"
                  className="calInput"
                  value={meeting.end_time}
                  onChange={(event) => updateMeeting(index, { end_time: event.target.value })}
                  required
                />
              </label>
            </div>

            <div className="calDayPicker" role="group" aria-label={`Days ${courseCode} meeting ${index + 1} runs`}>
              {WEEKDAY_CODES.map((code, day) => {
                const selected = meeting.days.includes(code);
                return (
                  <button
                    key={code}
                    type="button"
                    className={selected ? "calDay calDaySelected" : "calDay"}
                    onClick={() => toggleDay(index, code)}
                    aria-pressed={selected}
                    // M/T/W/T/F/S/S repeats two letters, so the visible label
                    // cannot be the accessible name.
                    aria-label={DAY_NAMES[day]}
                  >
                    {DAY_INITIALS[code]}
                  </button>
                );
              })}
            </div>

            <div className="calRow">
              <label className="calField">
                <span className="calFieldLabel">How often</span>
                <select
                  className="calInput"
                  value={meeting.interval}
                  onChange={(event) =>
                    updateMeeting(index, {
                      interval: Number(event.target.value),
                      // Weekly has no phase to choose, so the anchor goes with it
                      // rather than lingering as a value the API would ignore.
                      first_on: Number(event.target.value) > 1 ? meeting.first_on : null,
                    })
                  }
                >
                  {Array.from({ length: MAX_MEETING_INTERVAL }, (_, at) => at + 1).map((n) => (
                    <option key={n} value={n}>
                      {INTERVAL_LABELS[n] ?? `Every ${n} weeks`}
                    </option>
                  ))}
                </select>
              </label>

              {/* Only once there is a phase to choose. A weekly meeting starts
                  when the term does, and asking would imply otherwise. */}
              {meeting.interval > 1 && (
                <label className="calField">
                  <span className="calFieldLabel">First one on</span>
                  <input
                    type="date"
                    className="calInput"
                    value={meeting.first_on ?? ""}
                    onChange={(event) =>
                      updateMeeting(index, { first_on: event.target.value || null })
                    }
                  />
                </label>
              )}
            </div>

            {meeting.interval > 1 && (
              <p className="small-text muted">
                {meeting.first_on
                  ? "Runs from this date, then every " + meeting.interval + " weeks."
                  : "Without a date it starts in the term's first week, which puts it on the odd weeks."}
              </p>
            )}

            <div className="calRow">
              <label className="calField">
                <span className="calFieldLabel">Room</span>
                <input
                  className="calInput"
                  value={meeting.location ?? ""}
                  onChange={(event) =>
                    updateMeeting(index, { location: event.target.value || null })
                  }
                  placeholder="SWNG 222"
                />
              </label>

              {meetings.length > 1 && (
                <button
                  type="button"
                  className="calButton calButtonDanger"
                  onClick={() => setMeetings((current) => current.filter((_, at) => at !== index))}
                >
                  Remove
                </button>
              )}
            </div>
          </fieldset>
        ))}

        <button
          type="button"
          className="calButton"
          onClick={() => setMeetings((current) => [...current, blankMeeting()])}
        >
          Add a lab or discussion
        </button>

        {error && <p className="calError">{error}</p>}

        <div className="calFormActions">
          <button type="button" className="calButton" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button
            type="submit"
            className="calButton calButtonPrimary"
            disabled={saving || !hasTermDates}
          >
            {saving ? "Saving..." : "Save to calendar"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
