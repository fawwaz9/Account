import { useState } from "react";
import { fromIso } from "../../../shared/utils/dateUtils";

interface BlockedDatesProps {
  readonly value: string[];
  readonly onChange: (dates: string[]) => void;
  /** Only worth offering on something that repeats. */
  readonly repeats: boolean;
}

/**
 * Dates this one series does not run.
 *
 * Distinct from a term blackout, which is entered once and applies to every
 * class. This is the other case: a single lecture you already know is cancelled,
 * or a week you personally are away. Set here rather than only by skipping
 * occurrences after the fact, because a class you know does not run on the 14th
 * should never have appeared on the 14th.
 */
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
