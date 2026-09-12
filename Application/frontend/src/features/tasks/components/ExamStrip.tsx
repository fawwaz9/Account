import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchAgenda } from "../../calender/api";
import { EventOccurrence, EVENT_KIND_LABELS, EXAM_KINDS } from "../../calender/types";
import { useAuth } from "../../../app/auth/AuthContext";
import { addDays, clockTime, dueLabel, today } from "../../../shared/utils/dateUtils";

/** How far ahead an exam is worth knowing about while looking at this week's work. */
const HORIZON_DAYS = 30;

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

  useEffect(() => {
    if (!user) return;

    let cancelled = false;
    const from = today();
    fetchAgenda(user.id, from, addDays(from, HORIZON_DAYS))
      .then((occurrences) => {
        if (cancelled) return;
        setExams(occurrences.filter((item) => EXAM_KINDS.includes(item.kind)));
      })
      .catch(() => { if (!cancelled) setExams([]); });

    return () => { cancelled = true; };
  }, [user]);

  // Nothing to say rather than an empty box saying so: a student with no exams
  // booked does not need a permanent reminder that they have no exams booked.
  if (exams.length === 0) return null;

  return (
    <section className="examStrip" aria-label={`Exams in the next ${HORIZON_DAYS} days`}>
      <div className="examStripHead">
        <h2 className="examStripTitle">Coming up</h2>
        <Link className="examStripLink" to="/calendar">On the calendar</Link>
      </div>

      <ul className="examStripList">
        {exams.map((exam) => (
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
