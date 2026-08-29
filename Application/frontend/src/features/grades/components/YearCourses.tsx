import { YearSummary } from "../types";

interface YearCoursesProps {
  readonly title: string;
  readonly years: readonly YearSummary[];
  readonly emptyMessage: string;
}

/**
 * Past or Future courses, grouped by school year. Averages come from the API
 * so the "final grade, else average, else skip" rule lives in one place.
 */
export default function YearCourses({ title, years, emptyMessage }: YearCoursesProps) {
  return (
    <section className="yearSection">
      <h2>{title}</h2>

      {years.length === 0 ? (
        <p className="muted small-text">{emptyMessage}</p>
      ) : (
        <div className="yearGrid">
          {years.map((year) => (
            <div className="yearCard" key={year.school_year}>
              <span className="yearLabel">Year {year.school_year}</span>
              <span className="yearAverage">
                {year.average === null ? "–" : Math.round(year.average)}
              </span>
              <span className="yearCount small-text muted">
                {year.course_count} {year.course_count === 1 ? "course" : "courses"}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
