import { useEffect, useState } from "react";
import Modal from "../../../shared/components/Modal";
import { addShift, setShiftSchedule } from "../api";
import { Job, ShiftMeeting } from "../types";
import { Weekday } from "../../calender/types";
import { useAuth } from "../../../app/auth/AuthContext";
import { today } from "../../../shared/utils/dateUtils";

interface ShiftScheduleModalProps {
  readonly job: Job | null;
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

const DAY_INITIALS: Record<Weekday, string> = {
  MO: "M", TU: "T", WE: "W", TH: "T", FR: "F", SA: "S", SU: "S",
};
const DAY_NAMES: Record<Weekday, string> = {
  MO: "Monday", TU: "Tuesday", WE: "Wednesday", TH: "Thursday",
  FR: "Friday", SA: "Saturday", SU: "Sunday",
};
const DAY_ORDER: Weekday[] = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"];

function blankMeeting(): ShiftMeeting {
  return { days: [], start_time: "09:00", end_time: "17:00", location: null };
}

/**
 * Adding shifts to a job.
 *
 * One shift at a time is the default, because that is how part-time work
 * actually arrives: a rota posted a week ahead, different hours every week,
 * sometimes two shifts in a day. A form that only offered a weekly pattern
 * would be asking for a regularity most student jobs do not have.
 *
 * The pattern is still here for the jobs that do repeat, behind a disclosure.
 * Saving one replaces only the previous pattern — hand-entered shifts survive,
 * which they did not before this was split in two.
 */
export default function ShiftScheduleModal({ job, onClose, onSaved }: ShiftScheduleModalProps) {
  const { user } = useAuth();

  const [onDate, setOnDate] = useState(today());
  const [startTime, setStartTime] = useState("09:00");
  const [endTime, setEndTime] = useState("17:00");
  const [where, setWhere] = useState("");

  const [meetings, setMeetings] = useState<ShiftMeeting[]>([blankMeeting()]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState(0);

  useEffect(() => {
    setOnDate(today());
    setStartTime("09:00");
    setEndTime("17:00");
    setWhere("");
    setMeetings([blankMeeting()]);
    setError(null);
    setAdded(0);
  }, [job]);

  if (!job) return null;

  async function handleAddShift(event: React.FormEvent) {
    event.preventDefault();
    if (!user || !job) return;

    setSaving(true);
    setError(null);
    try {
      await addShift(user.id, job.id, {
        on_date: onDate,
        start_time: startTime,
        end_time: endTime,
        location: where.trim() || null,
      });
      // The dialog stays open and the date stays put: a rota is entered several
      // shifts at a time, and closing after each one would make that six clicks
      // per shift instead of two.
      setAdded((count) => count + 1);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add that shift");
    } finally {
      setSaving(false);
    }
  }

  function patchMeeting(index: number, change: Partial<ShiftMeeting>) {
    setMeetings((current) =>
      current.map((meeting, at) => (at === index ? { ...meeting, ...change } : meeting))
    );
  }

  function toggleDay(index: number, day: Weekday) {
    const meeting = meetings[index];
    patchMeeting(index, {
      days: meeting.days.includes(day)
        ? meeting.days.filter((code) => code !== day)
        : [...meeting.days, day],
    });
  }

  async function handleSavePattern() {
    if (!user || !job) return;

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
      setError(err instanceof Error ? err.message : "Could not save that pattern");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title={`Shifts · ${job.name}`} onClose={onClose} panelClassName="widePopup">
      <form className="calForm" onSubmit={handleAddShift}>
        <div className="calRow">
          <label className="calField">
            <span className="calFieldLabel">Date</span>
            <input
              type="date"
              className="calInput"
              value={onDate}
              onChange={(event) => setOnDate(event.target.value)}
              required
            />
          </label>

          <label className="calField">
            <span className="calFieldLabel">From</span>
            <input
              type="time"
              className="calInput"
              value={startTime}
              onChange={(event) => setStartTime(event.target.value)}
              required
            />
          </label>

          <label className="calField">
            <span className="calFieldLabel">To</span>
            <input
              type="time"
              className="calInput"
              value={endTime}
              onChange={(event) => setEndTime(event.target.value)}
              required
            />
          </label>

          <label className="calField">
            <span className="calFieldLabel">Where</span>
            <input
              className="calInput"
              value={where}
              onChange={(event) => setWhere(event.target.value)}
              placeholder="Front desk"
            />
          </label>
        </div>

        {error && <p className="calError">{error}</p>}

        <div className="calFormActions">
          {added > 0 && (
            <span className="small-text muted shiftAdded">
              {added} {added === 1 ? "shift" : "shifts"} added
            </span>
          )}
          <button type="button" className="calButton" onClick={onClose} disabled={saving}>
            {added > 0 ? "Done" : "Cancel"}
          </button>
          <button type="submit" className="calButton calButtonPrimary" disabled={saving}>
            {saving ? "Adding…" : "Add shift"}
          </button>
        </div>
      </form>

      {/* Behind a disclosure, because most student jobs do not repeat. The ones
          that do are better served by a pattern than by twelve identical
          entries. */}
      <details className="shiftPattern">
        <summary className="shiftPatternSummary">
          This job repeats the same days every week
        </summary>

        <p className="small-text muted">
          Replaces any pattern already set. Shifts you added by hand above are
          left alone.
        </p>

        {meetings.map((meeting, index) => (
          <div className="shiftMeeting" key={index}>
            <div className="calRow">
              <label className="calField">
                <span className="calFieldLabel">From</span>
                <input
                  type="time"
                  className="calInput"
                  value={meeting.start_time}
                  onChange={(event) => patchMeeting(index, { start_time: event.target.value })}
                />
              </label>

              <label className="calField">
                <span className="calFieldLabel">To</span>
                <input
                  type="time"
                  className="calInput"
                  value={meeting.end_time}
                  onChange={(event) => patchMeeting(index, { end_time: event.target.value })}
                />
              </label>

              <label className="calField">
                <span className="calFieldLabel">Where</span>
                <input
                  className="calInput"
                  value={meeting.location ?? ""}
                  onChange={(event) =>
                    patchMeeting(index, { location: event.target.value || null })
                  }
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
                    // M/T/W/T/F/S/S repeats two letters, so the visible label
                    // cannot be the accessible name.
                    aria-label={DAY_NAMES[code]}
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

        <div className="calFormActions">
          <button
            type="button"
            className="calButton"
            onClick={() => setMeetings((current) => [...current, blankMeeting()])}
          >
            Add another pattern
          </button>
          <button
            type="button"
            className="calButton calButtonPrimary"
            onClick={handleSavePattern}
            disabled={saving}
          >
            {saving ? "Saving…" : "Save pattern"}
          </button>
        </div>
      </details>
    </Modal>
  );
}
