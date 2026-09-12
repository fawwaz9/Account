import { EventOccurrence, EXAM_KINDS } from "../types";
import { Task } from "../../tasks/types";
import { clockTime, duration } from "../../../shared/utils/dateUtils";

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

  return (
    <button
      type="button"
      className={`calChip calChip-${occurrence.kind}${exam ? " calChipExam" : ""}`}
      onClick={() => onSelect(occurrence)}
      title={[occurrence.title, occurrence.location].filter(Boolean).join(" - ")}
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
  readonly onToggle: (task: Task) => void;
}

/**
 * A due task, in the day it is due.
 *
 * Checkable from here: a deadline you can see is one you want to tick off
 * without first navigating to another page.
 *
 * Shows the time when it has one. The month grid has no time axis to place it
 * on, so the alternative is a due time that is stored, entered and then never
 * shown anywhere -- which is how it went unnoticed that the calendar ignored it
 * entirely. The week view puts the same task on the clock instead.
 */
export function TaskChip({ task, onToggle }: TaskChipProps) {
  const due = clockTime(task.due_time);

  return (
    <button
      type="button"
      className={`calChip calChip-task${task.done ? " calChipDone" : ""}`}
      onClick={() => onToggle(task)}
      title={[task.title, due, task.course_code].filter(Boolean).join(" · ")}
      aria-label={
        `${task.done ? "Reopen" : "Complete"} ${task.title}` +
        (due ? `, due ${due}` : "")
      }
    >
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
  readonly busy: boolean;
}

/** What one occurrence expands to when it is selected. */
export default function EventCard({
  occurrence,
  onEdit,
  onSkip,
  onDelete,
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
      {occurrence.grade_id ? (
        <p className="calDetailMeta">
          From a grade with a due date. Change the date, or switch it back to a
          task, on the course page.
        </p>
      ) : (
        <div className="calDetailActions">
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
        </div>
      )}
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
