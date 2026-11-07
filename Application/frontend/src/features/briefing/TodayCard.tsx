import { useEffect, useState } from "react";
import { fetchDigest } from "./api";
import { Digest } from "./types";
import { useApiRefreshCount } from "../../shared/hooks/useApiRefresh";

/** Whose day. */
interface TodayCardProps {
  readonly userId: string;
}

/** Digest lines worth a warning under the schedule, by how they start, with their styling. */
const WARNINGS: { prefix: string; className: string }[] = [
  { prefix: "Overdue:", className: "todayLine todayLineWarn" },
  { prefix: "At risk:", className: "todayLine todayLineWarn" },
  { prefix: "Exam:", className: "todayLine todayLineExam" },
];

/** A time of day as the briefing writes it: "9am", "10:30am", "12pm". */
export function clock(time: string): string {
  const [hours, minutes] = time.split(":").map(Number);
  const suffix = hours < 12 ? "am" : "pm";
  const hour = hours % 12 === 0 ? 12 : hours % 12;
  return minutes ? `${hour}:${String(minutes).padStart(2, "0")}${suffix}` : `${hour}${suffix}`;
}

/** One row of the day: what, when, and where (a room, or a task's course). */
interface Row {
  readonly key: string;
  readonly what: string;
  readonly when: string;
  readonly where: string;
}

/** The day's events, then the tasks due today, as rows. */
function rows(digest: Digest): Row[] {
  const events = digest.events.map((event, index) => ({
    key: `event-${index}`,
    // A class reads as its course, as on the calendar; anything else as its title.
    what: event.course_code && event.kind !== "personal" ? event.course_code : event.title,
    when: event.start_time && event.end_time ? `${clock(event.start_time)} – ${clock(event.end_time)}` : "All day",
    where: event.location ?? "",
  }));
  const tasks = digest.due_today.map((task, index) => ({
    key: `task-${index}`,
    what: task.title,
    when: task.due_time ? `due ${clock(task.due_time)}` : "due today",
    where: task.course_code ?? "",
  }));
  return [...events, ...tasks];
}

/**
 * The Today card (Phase 4 item 6, redrawn 2026-11-07 for the big screen): the day's classes and
 * events with their times and rooms, the tasks due, then any overdue, at-risk or exam lines in
 * the briefing's own words. Renders nothing while loading or when the digest can't be read.
 */
export default function TodayCard({ userId }: TodayCardProps) {
  const [digest, setDigest] = useState<Digest | null>(null);
  const refreshed = useApiRefreshCount();

  useEffect(() => {
    let cancelled = false;
    fetchDigest(userId)
      .then((next) => { if (!cancelled) setDigest(next); })
      .catch(() => { if (!cancelled) setDigest(null); });
    return () => { cancelled = true; };
  }, [userId, refreshed]);

  if (!digest) return null;

  const day = new Date(`${digest.on_date}T00:00:00`).toLocaleDateString(
    undefined, { weekday: "short", month: "short", day: "numeric" },
  );
  const schedule = rows(digest);
  const warnings = digest.text.split("\n").slice(1).flatMap((line) => {
    const match = WARNINGS.find((warning) => line.startsWith(warning.prefix));
    return match ? [{ line, className: match.className }] : [];
  });

  return (
    <section className="gradeSummary dashCard todayCard" aria-label="Today">
      <h2 className="dashCardTitle">
        Today <span className="muted todayDate">{day}</span>
      </h2>
      {schedule.length > 0 ? (
        <table className="todayTable">
          <tbody>
            {schedule.map((row) => (
              <tr key={row.key}>
                <td>{row.what}</td>
                <td className="todayWhen">{row.when}</td>
                <td className="muted">{row.where}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted todayEmpty">Nothing on the calendar today.</p>
      )}
      {warnings.length > 0 && (
        <ul className="todayLines" aria-label="Needs attention">
          {warnings.map(({ line, className }) => <li key={line} className={className}>{line}</li>)}
        </ul>
      )}
    </section>
  );
}
