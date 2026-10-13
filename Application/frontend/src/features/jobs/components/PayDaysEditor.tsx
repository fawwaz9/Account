import { NthWeekday, PayDays, WeekendRule } from "../types";
import { Weekday } from "../../calender/types";

const MAX_ROWS = 4;

const POSITIONS: { n: NthWeekday["n"]; label: string }[] = [
  { n: 1, label: "1st" }, { n: 2, label: "2nd" }, { n: 3, label: "3rd" }, { n: 4, label: "4th" },
  { n: -1, label: "Last" },
];

const DAYS: { day: Weekday; label: string }[] = [
  { day: "MO", label: "Monday" }, { day: "TU", label: "Tuesday" }, { day: "WE", label: "Wednesday" },
  { day: "TH", label: "Thursday" }, { day: "FR", label: "Friday" }, { day: "SA", label: "Saturday" },
  { day: "SU", label: "Sunday" },
];

const WEEKEND: { rule: WeekendRule; label: string }[] = [
  { rule: "previous", label: "Paid the Friday before" },
  { rule: "next", label: "Paid the Monday after" },
  { rule: "keep", label: "Paid that day" },
];

interface PayDaysEditorProps {
  readonly value: PayDays;
  readonly onChange: (value: PayDays) => void;
}

/** The days a new pattern starts with: the first pay date's day of the month. */
export function startingPayDays(firstPayDate: string): PayDays {
  return {
    dates: [Number(firstPayDate.slice(8, 10))],
    last_day: false,
    nth_weekdays: [],
    weekend: "previous",
    until: null,
  };
}

/**
 * Pay on set days of the month: the shapes the repeat editor cannot say
 * (decided 2026-10-03). Either dates -- "the 15th and the last day" -- with
 * what happens when one lands on a weekend, or a weekday of the month -- "the
 * last Friday" -- which stands alone, since mixing the two is a schedule no
 * payroll runs.
 */
export default function PayDaysEditor({ value, onChange }: PayDaysEditorProps) {
  const byWeekday = value.nth_weekdays.length > 0;

  function setMode(weekday: boolean) {
    onChange(weekday
      ? { ...value, dates: [], last_day: false, nth_weekdays: [{ n: -1, day: "FR" }] }
      : { ...value, dates: [15], last_day: true, nth_weekdays: [] });
  }

  function setDate(index: number, text: string) {
    const day = Number(text);
    const dates = [...value.dates];
    dates[index] = Number.isFinite(day) ? day : 1;
    onChange({ ...value, dates });
  }

  function setNth(index: number, next: Partial<NthWeekday>) {
    const rows = value.nth_weekdays.map((row, at) => (at === index ? { ...row, ...next } : row));
    onChange({ ...value, nth_weekdays: rows });
  }

  return (
    <div className="payDays">
      <div className="calRow" role="radiogroup" aria-label="Pay days by">
        <label className="payDaysChoice">
          <input type="radio" checked={!byWeekday} onChange={() => setMode(false)} />
          Dates in the month
        </label>
        <label className="payDaysChoice">
          <input type="radio" checked={byWeekday} onChange={() => setMode(true)} />
          A weekday in the month
        </label>
      </div>

      {!byWeekday && (
        <>
          <div className="payDaysRows">
            {value.dates.map((day, index) => (
              <span key={index} className="payDaysRow">
                <input
                  type="number"
                  min={1}
                  max={31}
                  className="calInput payDaysDate"
                  value={day}
                  onChange={(event) => setDate(index, event.target.value)}
                  aria-label={`Pay date ${index + 1}, day of the month`}
                />
                {(value.dates.length > 1 || value.last_day) && (
                  <button
                    type="button"
                    className="calButton"
                    onClick={() => onChange({ ...value, dates: value.dates.filter((_, at) => at !== index) })}
                    aria-label={`Remove pay date ${index + 1}`}
                  >
                    ×
                  </button>
                )}
              </span>
            ))}
            {value.dates.length < MAX_ROWS && (
              <button
                type="button"
                className="calButton"
                onClick={() => onChange({ ...value, dates: [...value.dates, 1] })}
              >
                Add a date
              </button>
            )}
          </div>

          <label className="payDaysChoice">
            <input
              type="checkbox"
              checked={value.last_day}
              // Never left with nothing: unticking the last day with no dates
              // would be a schedule that pays on no day at all.
              disabled={value.last_day && value.dates.length === 0}
              onChange={(event) => onChange({ ...value, last_day: event.target.checked })}
            />
            The last day of the month
          </label>
          <p className="small-text muted">A date a month lacks, like the 31st in April, pays on its last day.</p>

          <label className="calField">
            <span className="calFieldLabel">If it lands on a weekend</span>
            <select
              className="calInput"
              value={value.weekend}
              onChange={(event) => onChange({ ...value, weekend: event.target.value as WeekendRule })}
            >
              {WEEKEND.map((option) => (
                <option key={option.rule} value={option.rule}>{option.label}</option>
              ))}
            </select>
          </label>
        </>
      )}

      {byWeekday && (
        <div className="payDaysRows">
          {value.nth_weekdays.map((row, index) => (
            <span key={index} className="payDaysRow">
              <select
                className="calInput"
                value={row.n}
                onChange={(event) => setNth(index, { n: Number(event.target.value) as NthWeekday["n"] })}
                aria-label={`Which week, pay day ${index + 1}`}
              >
                {POSITIONS.map((option) => (
                  <option key={option.n} value={option.n}>{option.label}</option>
                ))}
              </select>
              <select
                className="calInput"
                value={row.day}
                onChange={(event) => setNth(index, { day: event.target.value as Weekday })}
                aria-label={`Which day, pay day ${index + 1}`}
              >
                {DAYS.map((option) => (
                  <option key={option.day} value={option.day}>{option.label}</option>
                ))}
              </select>
              {value.nth_weekdays.length > 1 && (
                <button
                  type="button"
                  className="calButton"
                  onClick={() => onChange({ ...value, nth_weekdays: value.nth_weekdays.filter((_, at) => at !== index) })}
                  aria-label={`Remove pay day ${index + 1}`}
                >
                  ×
                </button>
              )}
            </span>
          ))}
          {value.nth_weekdays.length < MAX_ROWS && (
            <button
              type="button"
              className="calButton"
              onClick={() => onChange({ ...value, nth_weekdays: [...value.nth_weekdays, { n: 2, day: "TH" }] })}
            >
              Add a day
            </button>
          )}
        </div>
      )}

      <label className="calField">
        <span className="calFieldLabel">Last pay date (optional)</span>
        <input
          type="date"
          className="calInput"
          value={value.until ?? ""}
          onChange={(event) => onChange({ ...value, until: event.target.value || null })}
        />
      </label>
    </div>
  );
}
