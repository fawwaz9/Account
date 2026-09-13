import { useEffect, useState } from "react";
import Modal from "../../../shared/components/Modal";
import { setShiftSchedule } from "../api";
import { Job, ShiftMeeting } from "../types";
import { Weekday } from "../../calender/types";
import { useAuth } from "../../../app/auth/AuthContext";

interface ShiftScheduleModalProps {
  readonly job: Job | null;
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

const DAY_INITIALS: Record<Weekday, string> = {
  MO: "M", TU: "T", WE: "W", TH: "T", FR: "F", SA: "S", SU: "S",
};

const DAY_ORDER: Weekday[] = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"];

function blankMeeting(): ShiftMeeting {
  return { days: [], start_time: "09:00", end_time: "17:00", location: null };
}

/**
 * A job's recurring pattern, in the same form a course timetable uses.
 *
 * Deliberately the same shape: a work pattern and a timetable are the same
 * thing -- some days, a start, an end, repeated until it stops. Submitting it
 * replaces the pattern rather than adding to it, so fixing a time twice leaves
 * one schedule.
 */
export default function ShiftScheduleModal({ job, onClose, onSaved }: ShiftScheduleModalProps) {
  const { user } = useAuth();
  const [meetings, setMeetings] = useState<ShiftMeeting[]>([blankMeeting()]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setMeetings([blankMeeting()]);
    setError(null);
  }, [job]);

  if (!job) return null;

  function patch(index: number, change: Partial<ShiftMeeting>) {
    setMeetings((current) =>
      current.map((meeting, at) => (at === index ? { ...meeting, ...change } : meeting))
    );
  }

  function toggleDay(index: number, day: Weekday) {
    const meeting = meetings[index];
    patch(index, {
      days: meeting.days.includes(day)
        ? meeting.days.filter((code) => code !== day)
        : [...meeting.days, day],
    });
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user || !job) return;

    // A row with no days picked is an unused slot rather than an error, the
    // same rule the course timetable follows.
    const filled = meetings.filter((meeting) => meeting.days.length > 0);

    setSaving(true);
    setError(null);
    try {
      await setShiftSchedule(user.id, job.id, {
        meetings: filled,
        starts_on: job.started_on,
        ends_on: job.ended_on,
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save that schedule");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title={`Shifts · ${job.name}`} onClose={onClose} panelClassName="widePopup">
      <form className="calForm" onSubmit={handleSubmit}>
        <p className="small-text muted">
          Replaces this job's shifts. They run between the job's own start and end
          dates, and appear on the calendar like any other block.
        </p>

        {meetings.map((meeting, index) => (
          <div className="shiftMeeting" key={index}>
            <div className="calRow">
              <label className="calField">
                <span className="calFieldLabel">Starts</span>
                <input
                  type="time"
                  className="calInput"
                  value={meeting.start_time}
                  onChange={(e) => patch(index, { start_time: e.target.value })}
                />
              </label>

              <label className="calField">
                <span className="calFieldLabel">Ends</span>
                <input
                  type="time"
                  className="calInput"
                  value={meeting.end_time}
                  onChange={(e) => patch(index, { end_time: e.target.value })}
                />
              </label>

              <label className="calField">
                <span className="calFieldLabel">Where</span>
                <input
                  className="calInput"
                  value={meeting.location ?? ""}
                  onChange={(e) => patch(index, { location: e.target.value || null })}
                  placeholder="Front desk"
                />
              </label>
            </div>

            <div className="calDayPicker" role="group" aria-label={`Days pattern ${index + 1} runs`}>
              {DAY_ORDER.map((code) => {
                const selected = meeting.days.includes(code);
                return (
                  <button
                    key={code}
                    type="button"
                    className={selected ? "calDay calDaySelected" : "calDay"}
                    onClick={() => toggleDay(index, code)}
                    aria-pressed={selected}
                    aria-label={code}
                  >
                    {DAY_INITIALS[code]}
                  </button>
                );
              })}
            </div>

            {meetings.length > 1 && (
              <button
                type="button"
                className="calButton calButtonDanger"
                onClick={() => setMeetings((current) => current.filter((_, at) => at !== index))}
              >
                Remove this pattern
              </button>
            )}
          </div>
        ))}

        <button
          type="button"
          className="calButton"
          onClick={() => setMeetings((current) => [...current, blankMeeting()])}
        >
          Add another pattern
        </button>

        {error && <p className="calError">{error}</p>}

        <div className="calFormActions">
          <button type="button" className="calButton" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className="calButton calButtonPrimary" disabled={saving}>
            {saving ? "Saving…" : "Save shifts"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
