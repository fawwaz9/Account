import "../styles/dashboard.css";
import { useAuth } from "../app/auth/AuthContext";
import { useDashboard } from "../features/grades/hooks/useDashboard";
import { useBudgetGlance } from "../features/budget/hooks/useBudgetGlance";
import { useTimeGlance } from "../features/calender/hooks/useTimeGlance";
import { useWorkloadForecast } from "../features/calender/hooks/useWorkloadForecast";
import WorkloadHeadline from "../features/calender/components/WorkloadHeadline";
import { duration } from "../shared/utils/dateUtils";
import { formatMoney } from "../features/budget/money";
import GetStarted, { steps } from "../features/onboarding/GetStarted";
import DisappointmentQuestion from "../features/survey/DisappointmentQuestion";
import { PHONE_QUERY, useMediaQuery } from "../shared/hooks/useMediaQuery";
import { FreeBlock } from "../features/calender/types";

/** The browser's IANA time zone, or undefined when it cannot say. */
function browserZone(): string | undefined {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return undefined;
  }
}

/**
 * Home: grades, money and the week at a glance, plus the first-run checklist and the survey.
 * A phone gets three whole-dollar cards; the checklist waits until every source has loaded.
 */
export default function Dashboard() {
  const { user } = useAuth();

  const { summary, loading: summaryLoading, error: summaryError } = useDashboard();
  const {
    accounts, summary: budget, totalBalance, error: budgetError, loaded: budgetLoaded,
  } = useBudgetGlance();
  const { blocks: freeBlocks, load: weekLoad, loaded: weekLoaded, counts } = useTimeGlance();
  const phone = useMediaQuery(PHONE_QUERY);
  const forecast = useWorkloadForecast();
  // Nothing to say without a timetable, so the section stays away
  // rather than showing a row of zeroes.
  const hasWeek = Boolean(weekLoad && (weekLoad.booked_minutes > 0
    || weekLoad.task_count > 0 || freeBlocks.length > 0));

  const hasCourses = (summary?.total_courses ?? 0) > 0;

  // Only once every source has answered, and answered successfully. The steps
  // are claims about what exists, so a slow or failed read must not show a
  // student a list telling them to add courses they already have.
  const checklistReady = Boolean(
    user && !summaryLoading && !summaryError && summary && budgetLoaded && weekLoaded
  );
  const checklist = checklistReady && user ? steps({
    termSet: Boolean(user.current_school_year && user.current_semester),
    zone: user.preferences?.timezone,
    browserZone: browserZone(),
    courseCount: summary?.total_courses ?? 0,
    hasMoney: accounts.some((account) => account.balance !== 0)
      || (budget?.total_actual ?? 0) > 0,
    hasWeek: Boolean(weekLoad && (weekLoad.booked_minutes > 0 || weekLoad.task_count > 0)),
  }) : null;

  if (phone) {
    // The owner's phone sketch: no greeting, three cards, whole dollars. The
    // checklist and the survey stay while they apply, since both go away by
    // themselves; the rest of the desktop's extras do not fit a glance.
    const termLabel = user?.current_school_year && user?.current_semester
      ? `Year ${user.current_school_year} ${user.current_semester}`
      : "This term";

    return (
      <div className="dashboard phoneDashboard">
        {summaryError && <p className="muted" role="alert">{summaryError}</p>}
        {budgetError && <p className="muted" role="alert">{budgetError}</p>}

        {checklist && user && <GetStarted userId={user.id} steps={checklist} />}
        {user && <DisappointmentQuestion userId={user.id} />}

        {hasCourses && summary && (
          <section className="gradeSummary phoneCard" aria-label="Grades">
            <div className="phoneStats">
              <Stat value={summary.cumulative_average} label="Average" />
              {summary.cgpa !== null && <Stat value={summary.cgpa} label="CGPA" />}
              <Stat value={summary.total_courses} label="Courses" />
              <Stat value={summary.semester_average} label={termLabel} />
              <Stat value={summary.credits_completed} label="Credits completed" />
            </div>
          </section>
        )}

        {budget && (
          <section className="gradeSummary phoneCard" aria-label="Money">
            <div className="phoneStats">
              <Stat value={formatMoney(budget.total_actual, { whole: true })} label="Spent" />
              {budget.total_planned > 0 && (
                <Stat
                  value={formatMoney(budget.total_planned - budget.total_actual, { whole: true })}
                  label="Left"
                />
              )}
              <Stat value={formatMoney(totalBalance, { whole: true })} label="Net worth" />
            </div>
          </section>
        )}

        {hasWeek && weekLoad && (
          <section className="gradeSummary phoneCard" aria-label="This week">
            <h2 className="phoneCardTitle">This week</h2>
            <div className="phoneStats phoneStatsWeek">
              <Stat value={duration(weekLoad.booked_minutes) || "0h"} label="Booked" />
              <Stat value={weekLoad.task_count} label={weekLoad.task_count === 1 ? "Task due" : "Tasks due"} />
              {counts && <Stat value={counts.exams} label={counts.exams === 1 ? "Exam" : "Exams"} />}
              {counts && <Stat value={counts.shifts} label={counts.shifts === 1 ? "Shift" : "Shifts"} />}
            </div>
            {freeBlocks.length > 0 && (
              <p className="phoneFree">Free time: {longestFree(freeBlocks)}</p>
            )}
          </section>
        )}
      </div>
    );
  }

  return (
    <div className="dashboard">
      {/* The comma only appears with a name behind it. While /users/me is in
          flight this rendered "Welcome, " -- a greeting addressed to nobody. */}
      <h1 className="title">{user?.name ? `Welcome, ${user.name}` : "Welcome"}</h1>

      {summaryError && <p className="muted" role="alert">{summaryError}</p>}
      {/* Discarded entirely once, so a failed budget fetch rendered as no
          budget section at all -- indistinguishable from having no money. */}
      {budgetError && <p className="muted" role="alert">{budgetError}</p>}

      {checklist && user && <GetStarted userId={user.id} steps={checklist} />}
      {user && <DisappointmentQuestion userId={user.id} />}

      {hasCourses && summary && (
        <section className="gradeSummary">
          <div className="summaryStats">
            <div className="statBlock">
              <span className="statValue">{summary.cumulative_average}</span>
              <span className="statLabel">Average</span>
            </div>
            {/* Null when the GPA scale is switched off in Settings. */}
            {summary.cgpa !== null && (
              <div className="statBlock">
                <span className="statValue">{summary.cgpa}</span>
                <span className="statLabel">CGPA</span>
              </div>
            )}
            <div className="statBlock">
              <span className="statValue">{summary.total_courses}</span>
              <span className="statLabel">Courses</span>
            </div>
          </div>

          {summary.best_course && summary.weakest_course && (
            <div className="summaryCourses">
              <p>
                Strongest <strong>{summary.best_course.course_code}</strong>{" "}
                <span className="muted">{summary.best_course.average ?? "–"}</span>
              </p>
              <p>
                Weakest <strong>{summary.weakest_course.course_code}</strong>{" "}
                <span className="muted">{summary.weakest_course.average ?? "–"}</span>
              </p>
            </div>
          )}
        </section>
      )}

      {budget && (
        <section className="gradeSummary">
          <div className="summaryStats">
            <div className="statBlock">
              <span className="statValue">{formatMoney(totalBalance)}</span>
              {/* "Across accounts" while this was a plain sum, which was the
                  wrong name for it even then -- it counted debt as savings. */}
              <span className="statLabel">Net worth</span>
            </div>
            <div className="statBlock">
              <span className="statValue">{formatMoney(budget.total_actual)}</span>
              <span className="statLabel">Spent this month</span>
            </div>
            {budget.total_planned > 0 && (
              <div className="statBlock">
                <span className="statValue">
                  {formatMoney(budget.total_planned - budget.total_actual)}
                </span>
                <span className="statLabel">Left to spend</span>
              </div>
            )}
          </div>

          {budget.by_category.length > 0 && (
            <div className="summaryCourses">
              <p>
                Biggest this month <strong>{budget.by_category[0].category_name}</strong>{" "}
                <span className="muted">{formatMoney(budget.by_category[0].actual)}</span>
              </p>
            </div>
          )}
        </section>
      )}

      {/* The rolling seven days, ahead of the calendar-week glance: "is there
          time for what is coming" is the question a dashboard is opened for. */}
      {forecast && forecast.taskCount > 0 && (
        <section className="gradeSummary">
          <WorkloadHeadline forecast={forecast} />
        </section>
      )}

      {hasWeek && weekLoad && (
        <section className="gradeSummary">
          <div className="summaryStats">
            <div className="statBlock">
              <span className="statValue">{duration(weekLoad.booked_minutes) || "0h"}</span>
              <span className="statLabel">Booked this week</span>
            </div>
            <div className="statBlock">
              <span className="statValue">{weekLoad.task_count}</span>
              <span className="statLabel">
                {weekLoad.task_count === 1 ? "Task due" : "Tasks due"}
              </span>
            </div>
            {weekLoad.estimated_minutes > 0 && (
              <div className="statBlock">
                <span className="statValue">{duration(weekLoad.estimated_minutes)}</span>
                <span className="statLabel">
                  Estimated work{weekLoad.estimate_ratio != null && ` (× ${weekLoad.estimate_ratio.toFixed(2)})`}
                </span>
              </div>
            )}
          </div>

          {/* The two longest, because the point is "where could this go" and a
              list of every gap is a thing nobody reads on a dashboard. */}
          {freeBlocks.length > 0 && (
            <div className="summaryCourses">
              <p>
                Longest free{" "}
                {freeBlocks.slice(0, 2).map((block, index) => (
                  <span key={`${block.on_date}-${block.starts_at}`}>
                    {index > 0 && ", "}
                    <strong>{duration(block.minutes)}</strong>{" "}
                    <span className="muted">
                      {new Date(`${block.on_date}T00:00:00`).toLocaleDateString(
                        undefined, { weekday: "short" }
                      )}
                    </span>
                  </span>
                ))}
              </p>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

/** One figure with its label on a phone card. */
function Stat({ value, label }: { value: string | number; label: string }) {
  return (
    <div className="statBlock">
      <span className="statValue">{value}</span>
      <span className="statLabel">{label}</span>
    </div>
  );
}

/** The two longest free gaps this week, as "13h Sat, 7h Fri". */
function longestFree(blocks: FreeBlock[]): string {
  return blocks.slice(0, 2).map((block) => {
    const day = new Date(`${block.on_date}T00:00:00`).toLocaleDateString(undefined, { weekday: "short" });
    return `${duration(block.minutes)} ${day}`;
  }).join(", ");
}
