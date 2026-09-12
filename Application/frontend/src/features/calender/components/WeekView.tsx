import { useEffect, useRef } from "react";
import { CalendarDay } from "../hooks/useCalender";
import { EventOccurrence, EXAM_KINDS } from "../types";
import { Task } from "../../tasks/types";
import { TaskChip } from "./EventCard";
import { DAY_START, HOUR_HEIGHT, HOURS, OPENING_HOUR, place, placeTasks } from "../weekLayout";
import { clockTime, fromIso, hourLabel, today } from "../../../shared/utils/dateUtils";

const WEEKDAY_HEADINGS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

interface WeekViewProps {
  readonly days: CalendarDay[];
  readonly loading: boolean;
  readonly onSelectOccurrence: (occurrence: EventOccurrence) => void;
  readonly onToggleTask: (task: Task) => void;
  readonly onAddOnDay: (date: string) => void;
}

/**
 * One week against the clock, all twenty-four hours of it.
 *
 * The month grid answers "what is coming"; this answers "what does Tuesday
 * actually look like" — which needs the time axis, because the useful thing on
 * a timetable is as often the gaps as the blocks.
 *
 * Two grids rather than one, sharing a column template: the dates and the
 * all-day strip stay put while the hours scroll under them. CSS grid cannot
 * scroll a subset of its own rows, and a header that scrolls away takes with it
 * the only thing saying which column is which day.
 *
 * All-day items sit in that header rather than in the grid. They have no
 * position on a time axis, and pinning them to midnight would say something
 * false about when they happen. A task carrying a due time is not one of them:
 * it belongs on the clock at the minute it is due, which is what the header
 * cannot show.
 */
export default function WeekView({
  days,
  loading,
  onSelectOccurrence,
  onToggleTask,
  onAddOnDay,
}: WeekViewProps) {
  const now = today();
  const bodyRef = useRef<HTMLDivElement>(null);
  const gridHeight = HOURS.length * HOUR_HEIGHT;

  // Opened at the morning rather than at midnight. A full day is honest about
  // what exists, but nobody's week starts at 00:00, and eight empty hours is a
  // poor first impression of a timetable.
  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = (OPENING_HOUR - DAY_START) * HOUR_HEIGHT;
    }
  }, []);

  return (
    <div className="weekWrap">
      <div className="weekHeader">
        <div className="weekCorner" aria-hidden="true" />
        {days.map((day, index) => (
          <div
            key={day.date}
            className={day.date === now ? "weekHead weekHeadToday" : "weekHead"}
          >
            <span className="weekHeadDay">{WEEKDAY_HEADINGS[index]}</span>
            <button
              type="button"
              className="weekHeadDate"
              onClick={() => onAddOnDay(day.date)}
              aria-label={`Add an event on ${fromIso(day.date).toDateString()}`}
            >
              {fromIso(day.date).getDate()}
            </button>
          </div>
        ))}

        <div className="weekAllDayLabel">all day</div>
        {days.map((day) => (
          <div key={`allday-${day.date}`} className="weekAllDay">
            {day.occurrences
              .filter((item) => !item.start_time)
              .map((occurrence) => (
                <button
                  key={`${occurrence.event_id}-${occurrence.on_date}`}
                  type="button"
                  className={`calChip calChip-${occurrence.kind}${
                    EXAM_KINDS.includes(occurrence.kind) ? " calChipExam" : ""
                  }`}
                  onClick={() => onSelectOccurrence(occurrence)}
                >
                  <span className="calChipTitle">{occurrence.title}</span>
                </button>
              ))}
            {/* Only the ones with no time of their own. A task due at 14:00
                has a place in the grid below and does not belong up here. */}
            {day.tasks
              .filter((task) => !task.due_time)
              .map((task) => (
                <TaskChip key={task.id} task={task} onToggle={onToggleTask} />
              ))}
          </div>
        ))}
      </div>

      <div className="weekBody" ref={bodyRef}>
        <div className="weekGrid">
          <div className="weekHours" style={{ height: gridHeight }}>
            {HOURS.map((hour) => (
              <div key={hour} className="weekHour" style={{ height: HOUR_HEIGHT }}>
                <span className="weekHourLabel">{hourLabel(hour)}</span>
              </div>
            ))}
          </div>

          {days.map((day) => (
            <div key={`col-${day.date}`} className="weekColumn" style={{ height: gridHeight }}>
              {HOURS.map((hour) => (
                <div key={hour} className="weekSlot" style={{ height: HOUR_HEIGHT }} />
              ))}

              {place(day.occurrences).map((item) => {
                const top = ((item.startMinutes - DAY_START * 60) / 60) * HOUR_HEIGHT;
                const height = ((item.endMinutes - item.startMinutes) / 60) * HOUR_HEIGHT;
                const width = 100 / item.columns;
                const exam = EXAM_KINDS.includes(item.occurrence.kind);

                return (
                  <button
                    key={`${item.occurrence.event_id}-${item.occurrence.on_date}`}
                    type="button"
                    className={`weekBlock calChip-${item.occurrence.kind}${exam ? " weekBlockExam" : ""}`}
                    style={{
                      top,
                      height: Math.max(height, 18),
                      left: `${item.column * width}%`,
                      width: `calc(${width}% - 2px)`,
                    }}
                    onClick={() => onSelectOccurrence(item.occurrence)}
                    title={[
                      item.occurrence.title,
                      clockTime(item.occurrence.start_time),
                      item.occurrence.location,
                    ].filter(Boolean).join(" · ")}
                  >
                    <span className="weekBlockTitle">{item.occurrence.title}</span>
                    {/* Only when the block is tall enough to hold a second line;
                        otherwise the room pushes the title out of its own box. */}
                    {height >= HOUR_HEIGHT && item.occurrence.location && (
                      <span className="weekBlockWhere">{item.occurrence.location}</span>
                    )}
                  </button>
                );
              })}

              {/* Drawn after the blocks so a deadline inside a lecture is not
                  hidden behind it. A marker rather than a box: a task is due at
                  a moment and claims no span of the day. */}
              {placeTasks(day.tasks).map((item) => {
                const top = ((item.minutes - DAY_START * 60) / 60) * HOUR_HEIGHT;
                const width = 100 / item.columns;

                return (
                  <button
                    key={`due-${item.task.id}`}
                    type="button"
                    className={`weekDue${item.task.done ? " weekDueDone" : ""}`}
                    style={{
                      top,
                      left: `${item.column * width}%`,
                      width: `calc(${width}% - 2px)`,
                    }}
                    onClick={() => onToggleTask(item.task)}
                    title={[
                      item.task.title,
                      clockTime(item.task.due_time),
                      item.task.course_code,
                    ].filter(Boolean).join(" · ")}
                    aria-label={`${item.task.done ? "Reopen" : "Complete"} ${item.task.title}, due ${clockTime(item.task.due_time)}`}
                  >
                    <span className="weekDueMark" aria-hidden="true">
                      {item.task.done ? "✓" : "○"}
                    </span>
                    <span className="weekDueTitle">{item.task.title}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {loading && <p className="calMuted" role="status">Loading…</p>}
    </div>
  );
}
