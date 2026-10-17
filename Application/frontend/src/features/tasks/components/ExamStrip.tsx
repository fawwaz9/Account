import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchAgenda } from "../../calender/api";
import { EventOccurrence, EVENT_KIND_LABELS, EXAM_KINDS } from "../../calender/types";
import { useAuth } from "../../../app/auth/AuthContext";
import { addDays, clockTime, dueLabel, minutesOfDay } from "../../../shared/utils/dateUtils";
import { ZonedNow } from "../../../shared/utils/zonedNow";
import { useNow } from "../../calender/hooks/useNow";

/** How far ahead an exam is worth knowing about while looking at this week's work. */
const HORIZON_DAYS = 30;

/**
 * Not over yet. Today's exam goes once it ends -- at its end time, or at its
 * start when it has none, since sitting it is no time to be told it's coming.
 * One with no time at all stays the whole day: there's nothing to say it's done.
 */
export function stillAhead(exam: EventOccurrence, now: ZonedNow): boolean {
  if (exam.on_date !== now.date) return exam.on_date > now.date;
  const over = minutesOfDay(exam.end_time) ?? minutesOfDay(exam.start_time);
  return over === null || over > now.minutes;
}

/**
 * Midterms and finals coming up, above the work you can actually tick off.
 *
 * Read-only on purpose. An exam is not a task: there is nothing to check off,
 * and forcing one through a task row made it read as a chore that never quite
 * closes -- which is why dated grades already choose between raising a task and
 * drawing a calendar block. So this is a band that tells you what is coming and
 * links to the calendar, rather than rows in the list below.
 *
 * Thirty days rather than the list's fortnight because an exam is worth seeing
 * further out: there is nothing to do about it on the day, and the revision it
 * needs is the work that fills the fortnight.
 *
 * No endpoint of its own -- the agenda already expands repeats over any window,
 * so this is that call with a filter on it.
 */
export default function ExamStrip() {
  const { user } = useAuth();
  const [exams, setExams] = useState<EventOccurrence[]>([]);
  // The Settings zone's clock, ticking each minute: this morning's midterm
  // leaves at its end, and a tab left open overnight moves on to the new day.
  const now = useNow(user?.preferences?.timezone);
  const from = now.date;
  const userId = user?.id;

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
  }, [userId, from]);

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
