import { useState } from "react";
import { Link } from "react-router-dom";
import { EventOccurrence } from "../types";
import { leaveSharedEvent } from "../sharing";
import { clockTime } from "../../../shared/utils/dateUtils";

/** The viewer, the shared occurrence, and close and left callbacks. */
interface Props {
  readonly userId: string;
  readonly occurrence: EventOccurrence;
  readonly onClose: () => void;
  /** Called after leaving, so the calendar drops it. */
  readonly onLeft: () => void;
}

/**
 * Details of someone else's shared event or task: whose it is and who else is on it.
 * Offers leaving an event, confirmed in place; a shared task is handled on the Tasks page.
 */
export default function SharedOccurrenceCard({ userId, occurrence, onClose, onLeft }: Props) {
  const shared = occurrence.shared!;
  const [leaving, setLeaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const times = occurrence.start_time
    ? `${clockTime(occurrence.start_time)}${occurrence.end_time ? ` – ${clockTime(occurrence.end_time)}` : ""}`
    : shared.what === "task" ? "Due this day" : "All day";

  async function leave() {
    setBusy(true);
    setError(null);
    try {
      await leaveSharedEvent(userId, occurrence.event_id);
      onLeft();
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "That didn't work. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="calDetail">
      <p className="calDetailWhen">{times}</p>
      <p className="calDetailMeta">
        {shared.owner_name}&rsquo;s {shared.what} · with {shared.member_names.join(", ")}
      </p>
      {occurrence.location && <p className="calDetailMeta">{occurrence.location}</p>}
      {occurrence.notes && <p className="calDetailNotes">{occurrence.notes}</p>}
      {shared.what === "task" ? (
        <p className="calDetailMeta">
          Tick it or edit it on your <Link to="/tasks">Tasks page</Link>.
        </p>
      ) : (
        <p className="calDetailMeta">Only {shared.owner_name} can change it.</p>
      )}
      {error && <p className="small-text error" role="alert">{error}</p>}
      <div className="calDetailActions">
        <button type="button" className="calButton" onClick={onClose}>Close</button>
        {shared.what === "event" && (leaving ? (
          <>
            <span className="small-text">Leave it? You&rsquo;d need a new link from {shared.owner_name} to rejoin.</span>
            <button type="button" className="calButton calButtonDanger" disabled={busy} onClick={() => void leave()}>
              Leave
            </button>
            <button type="button" className="calButton" onClick={() => setLeaving(false)}>Stay</button>
          </>
        ) : (
          <button type="button" className="calButton" onClick={() => setLeaving(true)}>Leave this event</button>
        ))}
      </div>
    </div>
  );
}
