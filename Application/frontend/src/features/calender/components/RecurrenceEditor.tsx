import { Frequency, Recurrence, Weekday } from "../types";
import { WEEKDAY_CODES, weekdayCode } from "../../../shared/utils/dateUtils";

const WEEKDAY_LABELS: Record<Weekday, string> = {
  MO: "M", TU: "T", WE: "W", TH: "T", FR: "F", SA: "S", SU: "S",
};

const FREQUENCY_LABELS: Record<Frequency, string> = {
  daily: "day",
  weekly: "week",
  monthly: "month",
};

/** Which end the repeat has. Only one may be set, so the form asks which. */
type EndMode = "never" | "until" | "count";

interface RecurrenceEditorProps {
  readonly value: Recurrence | null;
  readonly onChange: (recurrence: Recurrence | null) => void;
  /** The event's start date, which is what a weekly repeat anchors to. */
  readonly startsOn: string;
}

/**
 * The repeat half of the event form.
 *
 * Offers exactly what the engine understands -- frequency, interval, weekdays,
 * and one end -- rather than a free-text RRULE. A control that can only express
 * supported rules is a cheaper guarantee than validating a richer string and
 * rejecting most of it.
 */
export default function RecurrenceEditor({ value, onChange, startsOn }: RecurrenceEditorProps) {
  const endMode: EndMode = value?.until ? "until" : value?.count ? "count" : "never";

  function setFrequency(freq: Frequency | "") {
    if (freq === "") {
      onChange(null);
      return;
    }

    onChange({
      freq,
      interval: value?.interval ?? 1,
      // The engine falls back to the start date's weekday, but showing that
      // day already selected is what makes the fallback legible.
      byday: freq === "weekly" ? (value?.byday?.length ? value.byday : [weekdayCode(startsOn)]) : [],
      until: value?.until ?? null,
      count: value?.count ?? null,
    });
  }

  function toggleDay(day: Weekday) {
    if (!value) return;

    const selected = value.byday.includes(day)
      ? value.byday.filter((code) => code !== day)
      : [...value.byday, day];

    // Never empty: an empty list means "the start date's weekday", which is a
    // different rule from the one the student was halfway through building.
    onChange({ ...value, byday: selected.length ? selected : value.byday });
  }

  function setEndMode(mode: EndMode) {
    if (!value) return;
    if (mode === "never") onChange({ ...value, until: null, count: null });
    if (mode === "until") onChange({ ...value, until: startsOn, count: null });
    if (mode === "count") onChange({ ...value, until: null, count: 10 });
  }

  return (
    <fieldset className="calRecurrence">
      <legend className="calFieldLabel">Repeat</legend>

      <div className="calRow">
        <select
          className="calInput"
          value={value?.freq ?? ""}
          onChange={(event) => setFrequency(event.target.value as Frequency | "")}
          aria-label="How often this repeats"
        >
          <option value="">Does not repeat</option>
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </select>

        {value && (
          <label className="calInlineField">
            <span className="calMuted">every</span>
            <input
              type="number"
              min={1}
              max={52}
              className="calInput calInputNarrow"
              value={value.interval}
              onChange={(event) =>
                onChange({ ...value, interval: Math.max(1, Number(event.target.value) || 1) })
              }
              aria-label={`Repeat every how many ${FREQUENCY_LABELS[value.freq]}s`}
            />
            <span className="calMuted">
              {FREQUENCY_LABELS[value.freq]}
              {value.interval === 1 ? "" : "s"}
            </span>
          </label>
        )}
      </div>

      {value?.freq === "weekly" && (
        <div className="calDayPicker" role="group" aria-label="Days of the week">
          {WEEKDAY_CODES.map((code, index) => {
            const selected = value.byday.includes(code);
            return (
              <button
                key={code}
                type="button"
                className={selected ? "calDay calDaySelected" : "calDay"}
                onClick={() => toggleDay(code)}
                aria-pressed={selected}
                // The visible label is one ambiguous letter -- T is Tuesday and
                // Thursday, S is Saturday and Sunday -- so the accessible name
                // has to be the real one.
                aria-label={["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][index]}
              >
                {WEEKDAY_LABELS[code]}
              </button>
            );
          })}
        </div>
      )}

      {value && (
        <div className="calRow">
          <select
            className="calInput"
            value={endMode}
            onChange={(event) => setEndMode(event.target.value as EndMode)}
            aria-label="When the repeat ends"
          >
            <option value="never">Ends: never</option>
            <option value="until">Ends: on a date</option>
            <option value="count">Ends: after a number of times</option>
          </select>

          {endMode === "until" && (
            <input
              type="date"
              className="calInput"
              value={value.until ?? ""}
              min={startsOn}
              onChange={(event) => onChange({ ...value, until: event.target.value || null })}
              aria-label="Last date of the repeat"
            />
          )}

          {endMode === "count" && (
            <input
              type="number"
              min={1}
              max={500}
              className="calInput calInputNarrow"
              value={value.count ?? 1}
              onChange={(event) =>
                onChange({ ...value, count: Math.max(1, Number(event.target.value) || 1) })
              }
              aria-label="Number of times it repeats"
            />
          )}
        </div>
      )}
    </fieldset>
  );
}
