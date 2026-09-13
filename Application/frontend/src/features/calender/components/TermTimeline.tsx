import { useMemo } from "react";
import { buildTimeline } from "../timeline";
import { Course } from "../../grades/types";
import { monthName, today } from "../../../shared/utils/dateUtils";

interface TermTimelineProps {
  readonly courses: Course[];
}

/**
 * Every course in the term on one axis.
 *
 * The month grid answers "what is this week"; this answers "what shape is the
 * term" — which courses overlap, where the gaps are, and how much of it has
 * already gone. Those are not visible anywhere else: a course's dates live on
 * its own page, so comparing six of them means six visits and a memory.
 *
 * Pure CSS bars, like the crunch radar. What matters is relative length and
 * overlap, and a charting dependency for two divs and a percentage would be a
 * poor trade.
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
