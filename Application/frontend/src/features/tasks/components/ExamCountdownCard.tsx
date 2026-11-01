import { ExamCountdown } from "../types";
import { clockTime, dueLabel, duration } from "../../../shared/utils/dateUtils";
import { EVENT_KIND_LABELS } from "../../calender/types";

/** The countdown, or null while it loads or when it failed. */
interface ExamCountdownCardProps {
  readonly countdown: ExamCountdown | null;
}

/** "Today", "Tomorrow", "In 3 days" for an exam's distance. */
export function whenText(daysLeft: number): string {
  if (daysLeft === 0) return "Today";
  if (daysLeft === 1) return "Tomorrow";
  return `In ${daysLeft} days`;
}

/**
 * Exam countdown (Phase 4 item 5): inside a week of a midterm or final, that course's
 * open work comes first, soonest due first. Renders nothing with no exam that close.
 */
export default function ExamCountdownCard({ countdown }: ExamCountdownCardProps) {
  if (!countdown || countdown.exams.length === 0) return null;

  return (
    <section className="examCountdown" aria-label="Exam countdown">
      {countdown.exams.map((exam) => {
        const name = `${exam.course_code ? `${exam.course_code} ` : ""}${EVENT_KIND_LABELS[exam.kind]}`;
        const more = exam.open_tasks - exam.tasks.length;
        return (
          <div key={`${exam.event_id}-${exam.on_date}`} className={`examCountdownItem examCountdown-${exam.kind}`}>
            <h2 className="examCountdownTitle">
              <span className="examCountdownDays">{whenText(exam.days_left)}</span>{" "}
              <span className="examCountdownName">{name}</span>
              {exam.start_time && <span className="muted small-text"> · {clockTime(exam.start_time)}</span>}
            </h2>

            {exam.tasks.length > 0 ? (
              <>
                <ul className="examCountdownTasks">
                  {exam.tasks.map((task) => (
                    <li key={task.id}>
                      <span>{task.title}</span>
                      {task.due_date && <span className="muted small-text"> · {dueLabel(task.due_date)}</span>}
                    </li>
                  ))}
                </ul>
                <p className="small-text muted examCountdownSum">
                  {exam.open_tasks} open task{exam.open_tasks === 1 ? "" : "s"} due by then
                  {more > 0 && `, ${more} more in the list below`}
                  {exam.estimated_minutes > 0 && ` · about ${duration(exam.estimated_minutes)} estimated`}
                </p>
              </>
            ) : (
              <p className="small-text muted examCountdownSum">
                {exam.course_id ? "Nothing open on this course before it." : "Not linked to a course."}
              </p>
            )}
          </div>
        );
      })}
    </section>
  );
}
