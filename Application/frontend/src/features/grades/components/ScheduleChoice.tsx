import { useState } from "react";
import { GradeCategory, GradeSchedule } from "../types";
import { today } from "../../../shared/utils/dateUtils";

/** What a date on a grade is for, including having no date at all. */
type Mode = "none" | GradeSchedule;

interface ScheduleChoiceProps {
  readonly dueDate: string | null;
  readonly scheduleAs: GradeSchedule;
  readonly onChange: (next: { due_date: string | null; schedule_as: GradeSchedule }) => void;
  /** Only used to word the calendar option for a midterm or a final. */
  readonly category: GradeCategory | null;
  /** Distinguishes the ids from the other form's when both are on the page. */
  readonly idPrefix: string;
}

function optionsFor(category: GradeCategory | null) {
  const exam = category === GradeCategory.MIDTERM || category === GradeCategory.FINAL;

  return [
    {
      value: "none" as const,
      label: "No date",
      hint: "Just a row in the gradebook, waiting for a score.",
    },
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
 * What a grade's date means: nothing, work to do, or something to attend.
 *
 * Owns the date and the choice together, and is always visible. Hiding the
 * choice until a date existed meant the only thing on screen was a field
 * labelled "due date" — so a calendar event looked like something the app
 * could not do, when it was one click away behind a control nobody could see.
 *
 * The hints carry the actual difference. "Calendar event" alone does not tell
 * you that you lose the tick-off, which is the whole trade being offered.
 */
export default function ScheduleChoice({
  dueDate,
  scheduleAs,
  onChange,
  category,
  idPrefix,
}: ScheduleChoiceProps) {
  const mode: Mode = dueDate ? scheduleAs : "none";

  // Remembered so switching to "No date" and back does not lose the date that
  // was already typed. Component state, because it is a convenience of this
  // control and not part of the grade.
  const [lastDate, setLastDate] = useState(dueDate ?? today());

  function pick(next: Mode) {
    if (next === "none") {
      onChange({ due_date: null, schedule_as: scheduleAs });
      return;
    }

    onChange({ due_date: dueDate ?? lastDate, schedule_as: next });
  }

  function setDate(value: string) {
    const date = value || null;
    if (date) setLastDate(date);
    // Keeping the current kind: changing when it is due is not a decision about
    // what kind of thing it is.
    onChange({ due_date: date, schedule_as: scheduleAs });
  }

  return (
    <fieldset className="scheduleChoice">
      <legend className="block text-sm text-slate-200">When is this?</legend>

      {optionsFor(category).map((option) => (
        <div key={option.value} className="scheduleOption">
          <input
            id={`${idPrefix}-${option.value}`}
            type="radio"
            name={`${idPrefix}-schedule`}
            value={option.value}
            checked={mode === option.value}
            onChange={() => pick(option.value)}
            className="--input h-4 w-4 border-slate-700 !bg-slate-900 !text-gold"
          />
          <label htmlFor={`${idPrefix}-${option.value}`} className="scheduleOptionLabel">
            <span className="scheduleOptionName">{option.label}</span>
            <span className="scheduleOptionHint">{option.hint}</span>
          </label>
        </div>
      ))}

      {/* Only once a date means something. With "No date" chosen there is
          nothing for it to hold. */}
      {mode !== "none" && (
        <label className="scheduleDate">
          <span className="scheduleOptionHint">
            {mode === GradeSchedule.TASK ? "Due on" : "Happens on"}
          </span>
          <input
            id={`${idPrefix}-date`}
            type="date"
            value={dueDate ?? ""}
            onChange={(event) => setDate(event.target.value)}
            className="--input rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white"
            required
          />
        </label>
      )}
    </fieldset>
  );
}
