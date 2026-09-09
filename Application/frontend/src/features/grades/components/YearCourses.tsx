import { YearSummary } from "../types";

interface YearCoursesProps {
  readonly title: string;
  readonly years: readonly YearSummary[];
  readonly emptyMessage: string;
  readonly selectedYear?: number | null;
  readonly onSelectYear?: (schoolYear: number) => void;
}

/**
 * Past or Future courses, grouped by school year. Averages come from the API
 * so the "final grade, else average, else skip" rule lives in one place.
 *
 * Each card opens that year's courses in the list beside it. Without that these
 * were dead ends: once the current term has no courses, every course in the
 * account sits behind one of these cards.
 */
export default function YearCourses({
  title,
  years,
  emptyMessage,
  selectedYear = null,
  onSelectYear,
}: YearCoursesProps) {
  return (
    <section className="yearSection">
      <h2>{title}</h2>

      {years.length === 0 ? (
        <p className="muted small-text">{emptyMessage}</p>
      ) : (
        <div className="yearGrid">
          {years.map((year) => {
            const active = selectedYear === year.school_year;
            return (
              <button
                type="button"
                className={active ? "yearCard yearCardActive" : "yearCard"}
                key={year.school_year}
                aria-pressed={active}
                onClick={() => onSelectYear?.(year.school_year)}
              >
                <span className="yearLabel">Year {year.school_year}</span>
                <span className="yearAverage">
                  {year.average === null ? "–" : Math.round(year.average)}
                </span>
                <span className="yearCount small-text muted">
                  {year.course_count} {year.course_count === 1 ? "course" : "courses"}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}
