import { EventOccurrence, EXAM_KINDS } from "../types";
import { Task } from "../../tasks/types";
import { hasSpecificTime } from "../../tasks/dueTime";
import { clockTime, duration } from "../../../shared/utils/dateUtils";
import { kindStyle } from "../kindColors";
import { useKindColors } from "../hooks/useKindColors";

interface EventCardProps {
  readonly occurrence: EventOccurrence;
  readonly onSelect: (occurrence: EventOccurrence) => void;
}

/**
 * One item in a day cell.
 *
 * Themed by kind: a midterm and a final each replace the class-block styling
 * with an exam card, so the week you actually have to worry about is legible at
 * a glance rather than reading like seven more lectures.
 */
export function EventChip({ occurrence, onSelect }: EventCardProps) {
  const exam = EXAM_KINDS.includes(occurrence.kind);
  const colors = useKindColors();

  return (
    <button
      type="button"
      className={`calChip calChip-${occurrence.kind}${exam ? " calChipExam" : ""}${occurrence.shared ? " calChipShared" : ""}`}
      style={kindStyle(occurrence.kind, colors)}
      onClick={() => onSelect(occurrence)}
      title={[occurrence.title, occurrence.location, occurrence.shared && `${occurrence.shared.owner_name}'s`]
        .filter(Boolean).join(" - ")}
    >
      {occurrence.start_time && (
        <span className="calChipTime">{clockTime(occurrence.start_time)}</span>
      )}
      <span className="calChipTitle">{occurrence.title}</span>
    </button>
  );
}

interface TaskChipProps {
  readonly task: Task;
  readonly onSelect: (task: Task) => void;
}

/**
 * A due task, in the day it is due.
 *
 * Opens the task editor -- the same one the task page opens, so a task has one
 * editor rather than two that can drift apart. This chip used to tick the task
 * off instead, which meant the calendar could do exactly one thing to a task
 * and a click meant to look at one finished it. Completing moved into the
 * editor, where it is a button that says what it does.
 *
 * Shows the time when it has one. The month grid has no time axis to place it
 * on, so the alternative is a due time that is stored, entered and then never
 * shown anywhere -- which is how it went unnoticed that the calendar ignored it
 * entirely. The week view puts the same task on the clock instead.
 */
export function TaskChip({ task, onSelect }: TaskChipProps) {
  // Not the end-of-day sentinel: "11:59pm" on nearly every chip is noise, and
  // says nothing the day it sits in has not already said.
  const due = hasSpecificTime(task) ? clockTime(task.due_time) : "";

  return (
    <button
      type="button"
      className={`calChip calChip-task${task.done ? " calChipDone" : ""}`}
      onClick={() => onSelect(task)}
      title={[task.title, due, task.course_code].filter(Boolean).join(" · ")}
      aria-label={`Edit ${task.title}` + (due ? `, due ${due}` : "")}
    >
      {/* State, not a control: the chip opens the editor, and completing is a
          button in there. A label saying "Complete" on something that opens a
          form is worse than no label. */}
      <span className="calChipMark" aria-hidden="true">{task.done ? "✓" : "○"}</span>
      {due && <span className="calChipWhen">{due}</span>}
      <span className="calChipTitle">{task.title}</span>
    </button>
  );
}

interface EventDetailProps {
  readonly occurrence: EventOccurrence;
  readonly onEdit: () => void;
  readonly onSkip: () => void;
  readonly onDelete: () => void;
  readonly onClose: () => void;
  readonly busy: boolean;
}

/** What one occurrence expands to when it is selected. */
export default function EventCard({
  occurrence,
  onEdit,
  onSkip,
  onDelete,
  onClose,
  busy,
}: EventDetailProps) {
  const times = occurrence.start_time
    ? `${clockTime(occurrence.start_time)}${
        occurrence.end_time ? ` – ${clockTime(occurrence.end_time)}` : ""
      }`
    : "All day";

  return (
    <div className="calDetail">
      <p className="calDetailWhen">{times}</p>
      {occurrence.course_code && <p className="calDetailMeta">{occurrence.course_code}</p>}
      {occurrence.location && <p className="calDetailMeta">{occurrence.location}</p>}
      {occurrence.notes && <p className="calDetailNotes">{occurrence.notes}</p>}

      {/* A block the gradebook owns is edited there, not here: deleting it on the
          calendar would only bring it back the next time the grade was saved. */}
      {occurrence.grade_id && (
        <p className="calDetailMeta">
          From a grade with a due date. Change the date, or switch it back to a
          task, on the course page.
        </p>
      )}

      {/* Close is here in both branches, and first.

          The dialog shell has no × and does not close on a backdrop click, so
          every other dialog in the app relies on its form's own Cancel. This
          one is read-only, and the grade branch used to render the sentence
          above and nothing else -- a popup with literally nothing to click,
          dismissable only by a keystroke nothing mentioned. The other branch
          was worse in its way: the nearest thing to a dismiss was "Cancel this
          one", which cancels the lecture.

          First in the row for that reason: the eye looks here for a way out,
          and what it finds should not be destructive. */}
      <div className="calDetailActions">
        <button type="button" className="calButton" onClick={onClose}>
          Close
        </button>

        {!occurrence.grade_id && (
          <>
            <button type="button" className="calButton" onClick={onEdit} disabled={busy}>
              Edit series
            </button>

            {/* Only a repeat can lose one date; a one-off has nothing left
                afterwards, so there the honest verb is delete. */}
            {occurrence.repeats && (
              <button type="button" className="calButton" onClick={onSkip} disabled={busy}>
                Cancel this one
              </button>
            )}

            <button type="button" className="calButton calButtonDanger" onClick={onDelete} disabled={busy}>
              {occurrence.repeats ? "Delete series" : "Delete"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

/** "1h 30m" for an occurrence, where both ends are known. */
export function occurrenceLength(occurrence: EventOccurrence): string {
  if (!occurrence.start_time || !occurrence.end_time) return "";

  const [startHour, startMinute] = occurrence.start_time.split(":").map(Number);
  const [endHour, endMinute] = occurrence.end_time.split(":").map(Number);
  return duration((endHour * 60 + endMinute) - (startHour * 60 + startMinute));
}
