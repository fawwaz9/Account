import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import CourseList from "../../features/grades/components/CourseList";
import AddCourseModal from "../../features/grades/components/AddCourseModal";
import CourseSearch from "../../features/grades/components/CourseSearch";
import SemesterSummary from "../../features/grades/components/SemesterSummary";
import CreditsBar from "../../features/grades/components/CreditsBar";
import YearCourses from "../../features/grades/components/YearCourses";
import { useCourses } from "../../features/grades/hooks/useCourses";
import { useDashboard } from "../../features/grades/hooks/useDashboard";

export default function GradesPage() {
  const { courses, loading, error, reload } = useCourses();
  const { summary, reload: reloadSummary } = useDashboard();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const navigate = useNavigate();

  // The list is the current term only. Anything else is reached through the
  // Past/Future sections or the search box, which spans every term.
  const currentCourses = useMemo(
    () => courses.filter((course) => course.term_bucket === "current"),
    [courses]
  );

  function handleCourseAdded() {
    reload();
    reloadSummary();
  }

  return (
    <>
      <div className="container gradesPage">
        <header className="gradesHeader">
          <h1 className="gradesTitle">Grades</h1>
        </header>

        <div className="gradesMenu">
          <button type="button" className="buttons backButton" onClick={() => navigate("/")}>
              &larr;
          </button>
          <CourseSearch />
        </div>

        <div className="gradesGrid">
          <div className="gradesColumn">
            <section>
              <div className="sectionHeading">
                <h2>Current Courses</h2>
                <button
                  type="button"
                  className="buttons addCourseButton"
                  onClick={() => setIsModalOpen(true)}
                >
                  Add Course
                </button>
              </div>

              {loading && <p className="muted">Loading courses...</p>}
              {error && <p className="muted">{error}</p>}
              {!loading && !error && courses.length === 0 && (
                <p className="muted">No courses yet. Use Add Course to create one.</p>
              )}
              {!loading && !error && courses.length > 0 && currentCourses.length === 0 && (
                <p className="muted">
                  No courses in your current term. Set it in Settings, or add one.
                </p>
              )}
              {currentCourses.length > 0 && <CourseList courses={currentCourses} />}
            </section>

            <YearCourses
              title="Past Courses"
              years={summary?.past_years ?? []}
              emptyMessage="Courses from earlier terms will appear here."
            />

            <YearCourses
              title="Future Courses"
              years={summary?.future_years ?? []}
              emptyMessage="Courses you plan for later years will appear here."
            />
          </div>

          <div className="gradesColumn">
            <SemesterSummary summary={summary} />

            {summary && (
              <CreditsBar
                completed={summary.credits_completed}
                inProgress={summary.credits_in_progress}
                target={summary.credit_target}
              />
            )}

            <div className="comingSoon">
              <span className="comingSoonLabel">Grade trend</span>
              <p className="small-text muted">
                Needs per-term history, which isn&apos;t recorded yet.
              </p>
            </div>

            <div className="comingSoon">
              <span className="comingSoonLabel">Attention</span>
              <p className="small-text muted">
                Needs exam dates and a target average, which aren&apos;t recorded yet.
              </p>
            </div>
          </div>
        </div>
      </div>

      <AddCourseModal
        open={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onCourseAdded={handleCourseAdded}
      />
    </>
  );
}
