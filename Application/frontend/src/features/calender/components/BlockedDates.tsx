import { useState } from "react";
import { fromIso } from "../../../shared/utils/dateUtils";

/** The series' skipped dates, their setter, and whether the event repeats. */
interface BlockedDatesProps {
  readonly value: string[];
  readonly onChange: (dates: string[]) => void;
  /** Only a repeating event offers this; otherwise nothing renders. */
  readonly repeats: boolean;
}

/** Edit the dates one repeating series skips; a break for every class belongs in blackouts. */
export default function BlockedDates({ value, onChange, repeats }: BlockedDatesProps) {
  const [pending, setPending] = useState("");

  if (!repeats) return null;

  function add() {
    if (!pending || value.includes(pending)) return;
    onChange([...value, pending].sort());
    setPending("");
  }

  return (
    <div className="calField">
      <span className="calFieldLabel">Skip these dates</span>

      {value.length > 0 && (
        <ul className="blockedDateList">
          {value.map((day) => (
            <li key={day}>
              <span>
                {fromIso(day).toLocaleDateString(undefined, {
                  weekday: "short", day: "numeric", month: "short",
                })}
              </span>
              <button
                type="button"
                className="bulkRemove"
                onClick={() => onChange(value.filter((other) => other !== day))}
                aria-label={`Stop skipping ${day}`}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="blockedDateAdd">
        <input
          className="calInput"
          type="date"
          value={pending}
          onChange={(event) => setPending(event.target.value)}
          aria-label="Date to skip"
        />
        <button
          type="button"
          className="calButton"
          onClick={add}
          disabled={!pending || value.includes(pending)}
        >
          Skip
        </button>
      </div>

      <span className="calHint">
        A reading break that applies to every class belongs in Blocked periods
        instead.
      </span>
    </div>
  );
}
