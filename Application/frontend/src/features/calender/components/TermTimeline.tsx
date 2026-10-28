import { useMemo } from "react";
import { buildTimeline } from "../timeline";
import { Course } from "../../grades/types";
import { monthName, today } from "../../../shared/utils/dateUtils";

/** The student's courses; only current-term ones are charted. */
interface TermTimelineProps {
  readonly courses: Course[];
}

/**
 * The current term's courses as bars on one date axis, with today marked.
 * Courses without dates are named below rather than dropped; nothing renders with no course.
 */
export default function TermTimeline({ courses }: TermTimelineProps) {
  // Only the term you are in. A finished course on this chart is history, and a
  // future one would stretch the axis past anything actionable.
  const current = useMemo(
    () => courses.filter((course) => course.term_bucket === "current"),
    [courses]
  );
  const timeline = useMemo(() => buildTimeline(current, today()), [current]);

  if (current.length === 0) return null;

  const { span, placed, undated, todayAt } = timeline;

  return (
    <section className="termLine" aria-label="Term timeline">
      <div className="sectionHeading">
        <h2>The term</h2>
        {span && (
          <span className="small-text muted">
            {monthName(span.starts_on, true)} – {monthName(span.ends_on, true)} ·{" "}
            {span.days} days
          </span>
        )}
      </div>

      {span && (
        <div className="termChart">
          {placed.map(({ course, left, width }) => (
            <div className="termRow" key={course.id}>
              <span className="termCode" title={course.name}>{course.code}</span>

              <div className="termTrack">
                {/* Drawn under the bars so a course running today is not cut in
                    half by its own marker. */}
                {todayAt !== null && (
                  <span className="termToday" style={{ left: `${todayAt}%` }} aria-hidden="true" />
                )}
                <span
                  className="termBar"
                  style={{ left: `${left}%`, width: `${width}%` }}
                  title={`${course.code}: ${course.start_date} to ${course.end_date}`}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Said rather than dropped. Most courses in this app carry no dates, and
          a chart showing three of six would under-report the term while looking
          complete. */}
      {undated.length > 0 && (
        <p className="small-text muted termUndated">
          {undated.length === current.length
            ? "No course this term has dates set, so there is nothing to chart yet."
            : `Not shown, with no dates set: ${undated.map((c) => c.code).join(", ")}`}
        </p>
      )}
    </section>
  );
}
