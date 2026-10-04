import { useEffect, useRef } from "react";
import { CalendarDay } from "../hooks/useCalender";
import { EventOccurrence, EXAM_KINDS } from "../types";
import { Task } from "../../tasks/types";
import { hasSpecificTime } from "../../tasks/dueTime";
import { TaskChip } from "./EventCard";
import { DAY_START, HOUR_HEIGHT, HOURS, OPENING_HOUR, place, placeTasks } from "../weekLayout";
import { clockTime, fromIso, hourLabel } from "../../../shared/utils/dateUtils";
import { useAuth } from "../../../app/auth/AuthContext";
import { useNow } from "../hooks/useNow";
import { useKindColors } from "../hooks/useKindColors";
import { kindStyle } from "../kindColors";

const WEEKDAY_HEADINGS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

interface WeekViewProps {
  readonly days: CalendarDay[];
  readonly loading: boolean;
  readonly onSelectOccurrence: (occurrence: EventOccurrence) => void;
  readonly onSelectTask: (task: Task) => void;
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
 * false about when they happen. A task due at a particular minute is not one of
 * them: it belongs on the clock, which is what the header cannot show. A task
 * due by the end of the day is, since that is what a bare due date means.
 */
export default function WeekView({
  days,
  loading,
  onSelectOccurrence,
  onSelectTask,
  onAddOnDay,
}: WeekViewProps) {
  // The Settings time zone, not the browser's: the backend's "today" comes from
  // it, and the highlighted column and the line below must agree with each
  // other and with every figure the server sends.
  const zone = useAuth().user?.preferences?.timezone;
  const now = useNow(zone);
  const colors = useKindColors();
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
            className={day.date === now.date ? "weekHead weekHeadToday" : "weekHead"}
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
                  style={kindStyle(occurrence.kind, colors)}
                  onClick={() => onSelectOccurrence(occurrence)}
                >
                  <span className="calChipTitle">{occurrence.title}</span>
                </button>
              ))}
            {/* Exactly what the grid below leaves out. A task due at 14:00 has
                a place on the clock; one due by the end of the day does not, and
                pinning it to 23:59 would bury it under the fold. */}
            {day.tasks
              .filter((task) => !hasSpecificTime(task))
              .map((task) => (
                <TaskChip key={task.id} task={task} onSelect={onSelectTask} />
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
                      ...kindStyle(item.occurrence.kind, colors),
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
                    onClick={() => onSelectTask(item.task)}
                    title={[
                      item.task.title,
                      clockTime(item.task.due_time),
                      item.task.course_code,
                    ].filter(Boolean).join(" · ")}
                    aria-label={`Edit ${item.task.title}, due ${clockTime(item.task.due_time)}`}
                  >
                    <span className="weekDueMark" aria-hidden="true">
                      {item.task.done ? "✓" : "○"}
                    </span>
                    <span className="weekDueTitle">{item.task.title}</span>
                  </button>
                );
              })}

              {/* The current minute, in today's column and nowhere else -- so a
                  week that is not this one draws no line at all, with no branch
                  of its own. Hidden from assistive technology: it would announce
                  a new time every minute, and the header already marks today. */}
              {day.date === now.date && (
                <div
                  className="weekNow"
                  style={{ top: ((now.minutes - DAY_START * 60) / 60) * HOUR_HEIGHT }}
                  aria-hidden="true"
                >
                  <span className="weekNowDot" />
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {loading && <p className="calMuted" role="status">Loading…</p>}
    </div>
  );
}
