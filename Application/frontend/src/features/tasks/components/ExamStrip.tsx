import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchAgenda } from "../../calender/api";
import { EventOccurrence, EVENT_KIND_LABELS, EXAM_KINDS } from "../../calender/types";
import { useAuth } from "../../../app/auth/AuthContext";
import { addDays, clockTime, dueLabel, minutesOfDay } from "../../../shared/utils/dateUtils";
import { ZonedNow } from "../../../shared/utils/zonedNow";
import { useNow } from "../../calender/hooks/useNow";
import { useApiRefreshCount } from "../../../shared/hooks/useApiRefresh";

/** How many days ahead the strip looks for exams. */
const HORIZON_DAYS = 30;

/**
 * True until an exam is over: today's leaves at its end time, or its start if it has no end;
 * one with no time at all stays the whole day.
 */
export function stillAhead(exam: EventOccurrence, now: ZonedNow): boolean {
  if (exam.on_date !== now.date) return exam.on_date > now.date;
  const over = minutesOfDay(exam.end_time) ?? minutesOfDay(exam.start_time);
  return over === null || over > now.minutes;
}

/**
 * Read-only band of midterms and finals in the next 30 days, above the task list.
 * Built from the agenda call with a filter; renders nothing when no exam is ahead.
 */
export default function ExamStrip() {
  const { user } = useAuth();
  const [exams, setExams] = useState<EventOccurrence[]>([]);
  // The Settings zone's clock, ticking each minute: this morning's midterm
  // leaves at its end, and a tab left open overnight moves on to the new day.
  const now = useNow(user?.preferences?.timezone);
  const from = now.date;
  const userId = user?.id;
  // Read again when a background refetch finds something new (audit #35).
  const refreshed = useApiRefreshCount();

  useEffect(() => {
    if (!userId) return;

    let cancelled = false;
    fetchAgenda(userId, from, addDays(from, HORIZON_DAYS))
      .then((occurrences) => {
        if (cancelled) return;
        setExams(occurrences.filter((item) => EXAM_KINDS.includes(item.kind)));
      })
      .catch(() => { if (!cancelled) setExams([]); });

    return () => { cancelled = true; };
  }, [userId, from, refreshed]);

  const ahead = exams.filter((exam) => stillAhead(exam, now));

  // Nothing to say rather than an empty box saying so: a student with no exams
  // booked does not need a permanent reminder that they have no exams booked.
  if (ahead.length === 0) return null;

  return (
    <section className="examStrip" aria-label={`Exams in the next ${HORIZON_DAYS} days`}>
      <div className="examStripHead">
        <h2 className="examStripTitle">Coming up</h2>
        <Link className="examStripLink" to="/calendar">On the calendar</Link>
      </div>

      <ul className="examStripList">
        {ahead.map((exam) => (
          <li
            key={`${exam.event_id}-${exam.on_date}`}
            className={`examCard examCard-${exam.kind}`}
          >
            <span className="examWhen">{dueLabel(exam.on_date)}</span>
            <span className="examTitle">
              {exam.course_code ? `${exam.course_code} ` : ""}
              {EVENT_KIND_LABELS[exam.kind]}
            </span>
            <span className="examWhere">
              {[clockTime(exam.start_time), exam.location].filter(Boolean).join(" · ")}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
