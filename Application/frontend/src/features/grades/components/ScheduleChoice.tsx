import { GradeCategory, GradeSchedule } from "../types";

interface ScheduleChoiceProps {
  readonly value: GradeSchedule;
  readonly onChange: (value: GradeSchedule) => void;
  /** Only used to word the event option for a midterm or a final. */
  readonly category: GradeCategory | null;
  readonly idPrefix: string;
}

/** The two things a date can mean, each said plainly enough to pick between. */
function optionsFor(category: GradeCategory | null) {
  const exam = category === GradeCategory.MIDTERM || category === GradeCategory.FINAL;

  return [
    {
      value: GradeSchedule.TASK,
      label: "Due date",
      hint: "Adds it to your tasks. It ticks itself off when you enter a score.",
    },
    {
      value: GradeSchedule.EVENT,
      label: "Calendar event",
      hint: exam
        ? "Puts it on the calendar as an exam. Nothing to tick off."
        : "Puts it on the calendar only. Nothing to tick off.",
    },
  ];
}

/**
 * Whether a dated grade becomes a task or a calendar block.
 *
 * Shown only once a date exists, because without one it decides nothing. The
 * hints carry the actual difference: the label "Calendar event" alone does not
 * tell you that you lose the tick-off, which is the whole trade.
 */
export default function ScheduleChoice({
  value,
  onChange,
  category,
  idPrefix,
}: ScheduleChoiceProps) {
  return (
    <fieldset className="scheduleChoice">
      <legend className="block text-sm text-slate-200">What should this date do?</legend>

      {optionsFor(category).map((option) => (
        <div key={option.value} className="scheduleOption">
          <input
            id={`${idPrefix}-${option.value}`}
            type="radio"
            name={`${idPrefix}-schedule`}
            value={option.value}
            checked={value === option.value}
            onChange={() => onChange(option.value)}
            className="--input h-4 w-4 border-slate-700 !bg-slate-900 !text-gold"
          />
          <label htmlFor={`${idPrefix}-${option.value}`} className="scheduleOptionLabel">
            <span className="scheduleOptionName">{option.label}</span>
            <span className="scheduleOptionHint">{option.hint}</span>
          </label>
        </div>
      ))}
    </fieldset>
  );
}
