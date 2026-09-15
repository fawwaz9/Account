import { useState } from "react";
import { GradeCategory, GradeSchedule } from "../types";
import { duration, today } from "../../../shared/utils/dateUtils";

/** What a date on a grade is for, including having no date at all. */
type Mode = "none" | GradeSchedule;

/** Shared by the three fields below, so they cannot drift apart visually. */
const FIELD =
  "--input rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white";

/** Everything this control owns, changed as one. */
export interface Scheduling {
  due_date: string | null;
  due_time: string | null;
  duration_minutes: number | null;
  schedule_as: GradeSchedule;
}

interface ScheduleChoiceProps {
  readonly dueDate: string | null;
  readonly dueTime: string | null;
  readonly durationMinutes: number | null;
  readonly scheduleAs: GradeSchedule;
  readonly onChange: (next: Scheduling) => void;
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
  dueTime,
  durationMinutes,
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

  /** Each clearing takes what depends on it, the way the API does. */
  function emit(next: Partial<Scheduling>) {
    const merged: Scheduling = {
      due_date: dueDate,
      due_time: dueTime,
      duration_minutes: durationMinutes,
      schedule_as: scheduleAs,
      ...next,
    };

    if (merged.due_date === null) merged.due_time = null;
    if (merged.due_time === null) merged.duration_minutes = null;
    // A task is a moment, not a block. Switching a midterm back to work-to-do
    // must not leave two hours on it that nothing reads and nothing shows.
    if (merged.schedule_as !== GradeSchedule.EVENT) merged.duration_minutes = null;

    onChange(merged);
  }

  function pick(next: Mode) {
    if (next === "none") {
      emit({ due_date: null });
      return;
    }

    emit({ due_date: dueDate ?? lastDate, schedule_as: next });
  }

  function setDate(value: string) {
    const date = value || null;
    if (date) setLastDate(date);
    // Keeping the current kind: changing when it is due is not a decision about
    // what kind of thing it is.
    emit({ due_date: date });
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
        <div className="scheduleWhen">
          <label className="scheduleDate">
            <span className="scheduleOptionHint">
              {mode === GradeSchedule.TASK ? "Due on" : "Happens on"}
            </span>
            <input
              id={`${idPrefix}-date`}
              type="date"
              value={dueDate ?? ""}
              onChange={(event) => setDate(event.target.value)}
              className={FIELD}
              required
            />
          </label>

          {/* Optional, and blank on purpose. Nothing is pre-filled because a
              guessed 09:00 reads on the calendar as a fact. Blank means no
              particular time: the end of the day for a task, an all-day block
              for a midterm. */}
          <label className="scheduleDate">
            <span className="scheduleOptionHint">
              {mode === GradeSchedule.TASK ? "Due at" : "Starts at"}
            </span>
            <input
              id={`${idPrefix}-time`}
              type="time"
              value={dueTime ?? ""}
              onChange={(event) => emit({ due_time: event.target.value || null })}
              className={FIELD}
            />
          </label>

          {/* A length rather than an end time: "the midterm is two hours" is
              what you know, and an end worked out from a start cannot end
              before it. Only on the calendar side, and only once there is a
              start for it to run from -- a task is a moment and an all-day
              block has no length. */}
          {mode === GradeSchedule.EVENT && dueTime && (
            <label className="scheduleDate">
              <span className="scheduleOptionHint">
                For {duration(durationMinutes) || "how long?"}
              </span>
              <input
                id={`${idPrefix}-duration`}
                type="number"
                min={5}
                max={1440}
                step={5}
                value={durationMinutes ?? ""}
                // Number("") is 0, which would claim the exam takes no time.
                onChange={(event) =>
                  emit({
                    duration_minutes:
                      event.target.value === "" ? null : Number(event.target.value),
                  })
                }
                placeholder="mins"
                aria-label="How many minutes it runs"
                className={FIELD}
              />
            </label>
          )}
        </div>
      )}
    </fieldset>
  );
}
