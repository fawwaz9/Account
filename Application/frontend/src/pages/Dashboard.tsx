import "../styles/dashboard.css";
import { useAuth } from "../app/auth/AuthContext";
import { useDashboard } from "../features/grades/hooks/useDashboard";
import { useBudgetGlance } from "../features/budget/hooks/useBudgetGlance";
import { useTimeGlance } from "../features/calender/hooks/useTimeGlance";
import { duration } from "../shared/utils/dateUtils";
import { formatMoney } from "../features/budget/money";
import GetStarted, { steps } from "../features/onboarding/GetStarted";
import DisappointmentQuestion from "../features/survey/DisappointmentQuestion";
import { PHONE_QUERY, useMediaQuery } from "../shared/hooks/useMediaQuery";
import { FreeBlock } from "../features/calender/types";
import TodayCard from "../features/briefing/TodayCard";

/** The browser's IANA time zone, or undefined when it cannot say. */
function browserZone(): string | undefined {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return undefined;
  }
}

/**
 * Home: grades, the week and the month's money as three cards, then Today, plus the first-run
 * checklist and the survey. A phone gets the same cards stacked, with no greeting or Today;
 * the checklist waits until every source has loaded.
 */
export default function Dashboard() {
  const { user } = useAuth();

  const { summary, loading: summaryLoading, error: summaryError } = useDashboard();
  const {
    accounts, summary: budget, totalBalance, error: budgetError, loaded: budgetLoaded,
  } = useBudgetGlance();
  const { blocks: freeBlocks, load: weekLoad, loaded: weekLoaded, counts } = useTimeGlance();
  const phone = useMediaQuery(PHONE_QUERY);
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

  const termLabel = user?.current_school_year && user?.current_semester
    ? `Year ${user.current_school_year} ${user.current_semester}`
    : "This term";

  if (phone) {
    // The owner's phone sketch: no greeting, three cards, whole dollars. The
    // checklist and the survey stay while they apply, since both go away by
    // themselves.

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

  // The month the money card covers, as its title: "November".
  const month = new Date().toLocaleDateString(undefined, { month: "long" });

  // The owner's big-screen sketch (2026-11-07): the greeting, three cards in a row (grades,
  // this week, the month's money), then Today. The details live on each page.
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

      <div className="dashCards">
        {hasCourses && summary && (
          <section className="gradeSummary dashCard" aria-label="Grades">
            <div className="dashStats">
              <Stat value={summary.cumulative_average} label="Average" />
              <Stat value={summary.semester_average} label={termLabel} />
              {/* Null when the GPA scale is switched off in Settings. */}
              {summary.cgpa !== null && <Stat value={summary.cgpa} label="CGPA" />}
              <Stat value={summary.credits_completed} label="Credits completed" />
            </div>
          </section>
        )}

        {hasWeek && weekLoad && (
          <section className="gradeSummary dashCard" aria-label="This week">
            <h2 className="dashCardTitle">This week</h2>
            <div className="dashStats">
              <Stat value={duration(weekLoad.booked_minutes) || "0h"} label="Booked" />
              <Stat value={weekLoad.task_count} label={weekLoad.task_count === 1 ? "Task due" : "Tasks due"} />
              {counts && <Stat value={counts.exams} label={counts.exams === 1 ? "Exam" : "Exams"} />}
              {counts && <Stat value={counts.shifts} label={counts.shifts === 1 ? "Shift" : "Shifts"} />}
            </div>
            {freeBlocks.length > 0 && <p className="phoneFree">Free time: {longestFree(freeBlocks)}</p>}
          </section>
        )}

        {budget && (
          <section className="gradeSummary dashCard" aria-label="Money">
            <h2 className="dashCardTitle">{month}</h2>
            <div className="dashStats">
              <Stat value={formatMoney(budget.total_actual, { whole: true })} label="Spent" />
              {budget.total_planned > 0 && (
                <Stat value={formatMoney(budget.total_planned - budget.total_actual, { whole: true })} label="Left" />
              )}
              {/* "Across accounts" while this was a plain sum, which was the
                  wrong name for it even then -- it counted debt as savings. */}
              <Stat value={formatMoney(totalBalance, { whole: true })} label="Net worth" />
            </div>
          </section>
        )}
      </div>

      {/* Phase 4 item 6: the day's schedule, then what needs attention. */}
      <div className="dashCards">
        {user && <TodayCard userId={user.id} />}
      </div>
    </div>
  );
}

/** One figure with its label on a card. */
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
