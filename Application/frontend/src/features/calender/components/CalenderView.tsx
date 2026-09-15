import { CalendarDay } from "../hooks/useCalender";
import { EventOccurrence } from "../types";
import { Task } from "../../tasks/types";
import { EventChip, TaskChip } from "./EventCard";
import { fromIso, isSameMonth, today } from "../../../shared/utils/dateUtils";

const WEEKDAY_HEADINGS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

interface CalenderViewProps {
  /** Any date inside the month being drawn. */
  readonly month: string;
  readonly days: CalendarDay[];
  readonly loading: boolean;
  readonly onSelectOccurrence: (occurrence: EventOccurrence) => void;
  readonly onSelectTask: (task: Task) => void;
  readonly onAddOnDay: (date: string) => void;
}

/**
 * The month grid.
 *
 * Always six rows: a month needing five would otherwise make the page jump in
 * height as you page through a term. Days outside the month stay visible but
 * muted, because a deadline on the 1st matters while you are still looking at
 * the previous month.
 */
export default function CalenderView({
  month,
  days,
  loading,
  onSelectOccurrence,
  onSelectTask,
  onAddOnDay,
}: CalenderViewProps) {
  const now = today();

  return (
    <section className="calShell" aria-label="Month view">
      {/* A spinner rather than an empty grid: the month's shape stays put while
          the new one loads, so paging does not flash. */}
      {loading && <span className="calMuted calGridLoading" role="status">Loading…</span>}

      <div className="calWeekdays" aria-hidden="true">
        {WEEKDAY_HEADINGS.map((label) => (
          <span key={label} className="calWeekday">{label}</span>
        ))}
      </div>

      <div className="calGrid">
        {days.map((day) => {
          const inMonth = isSameMonth(day.date, month);
          const isToday = day.date === now;

          return (
            <div
              key={day.date}
              className={[
                "calCell",
                inMonth ? "" : "calCellOutside",
                isToday ? "calCellToday" : "",
              ].filter(Boolean).join(" ")}
            >
              {/* The number is the add control: clicking an empty day is the
                  fastest way to put something on it, and a separate "+" in
                  every cell would be 42 buttons of visual noise. */}
              <button
                type="button"
                className="calCellDate"
                onClick={() => onAddOnDay(day.date)}
                aria-label={`Add an event on ${fromIso(day.date).toDateString()}`}
              >
                {fromIso(day.date).getDate()}
              </button>

              <div className="calCellItems">
                {day.occurrences.map((occurrence) => (
                  <EventChip
                    key={`${occurrence.event_id}-${occurrence.on_date}`}
                    occurrence={occurrence}
                    onSelect={onSelectOccurrence}
                  />
                ))}
                {day.tasks.map((task) => (
                  <TaskChip key={task.id} task={task} onSelect={onSelectTask} />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
