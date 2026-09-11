import { useMemo, useState } from "react";
import CourseList from "../../features/grades/components/CourseList";
import AddCourseModal from "../../features/grades/components/AddCourseModal";
import CourseSearch from "../../features/grades/components/CourseSearch";
import SemesterSummary from "../../features/grades/components/SemesterSummary";
import CreditsBar from "../../features/grades/components/CreditsBar";
import YearCourses from "../../features/grades/components/YearCourses";
import AttentionPanel from "../../features/grades/components/AttentionPanel";
import GradeTrendChart from "../../features/grades/components/GradeTrendChart";
import { useCourses } from "../../features/grades/hooks/useCourses";
import { useDashboard } from "../../features/grades/hooks/useDashboard";
import { Course } from "../../features/grades/types";
import { useAuth } from "../../app/auth/AuthContext";

interface TermGroup {
  semester: string;
  courses: Course[];
}

export default function GradesPage() {
  const { courses, loading, error, reload } = useCourses();
  const { summary, reload: reloadSummary } = useDashboard();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const { user } = useAuth();

  // The default list is the current term only. Everything else is reached
  // through a year card or the search box, which spans every term.
  const currentCourses = useMemo(
    () => courses.filter((course) => course.term_bucket === "current"),
    [courses]
  );

  // The API returns courses sorted by year, then term order, then code, so
  // consecutive runs are already the term groups -- no need for the client to
  // know what follows Fall.
  const selectedTerms = useMemo<TermGroup[]>(() => {
    if (selectedYear === null) return [];

    const groups: TermGroup[] = [];
    for (const course of courses) {
      if (course.year !== selectedYear) continue;

      const last = groups[groups.length - 1];
      if (last && last.semester === course.semester) {
        last.courses.push(course);
      } else {
        groups.push({ semester: course.semester, courses: [course] });
      }
    }
    return groups;
  }, [courses, selectedYear]);

  function handleCourseAdded() {
    reload();
    reloadSummary();
  }

  const viewingYear = selectedYear !== null;

  return (
    <>
      <div className="container gradesPage">
        <div className="gradesMenu">
          <h1 className="gradesTitle">Grades</h1>
          <CourseSearch />
        </div>

        <div className="gradesGrid">
          <div className="gradesColumn">
            <section>
              <div className="sectionHeading">
                <h2>{viewingYear ? `Year ${selectedYear}` : "Current Courses"}</h2>

                {viewingYear ? (
                  <button
                    type="button"
                    className="buttons addCourseButton"
                    onClick={() => setSelectedYear(null)}
                  >
                    Current Courses
                  </button>
                ) : (
                  <button
                    type="button"
                    className="buttons addCourseButton"
                    onClick={() => setIsModalOpen(true)}
                  >
                    Add Course
                  </button>
                )}
              </div>

              {loading && <p className="muted">Loading courses...</p>}
              {error && <p className="muted">{error}</p>}

              {!loading && !error && viewingYear && (
                <div className="termGroups">
                  {selectedTerms.map((group) => (
                    <div className="termGroup" key={group.semester}>
                      <h3 className="termHeading">{group.semester}</h3>
                      <CourseList courses={group.courses} />
                    </div>
                  ))}
                </div>
              )}

              {!loading && !error && !viewingYear && (
                <>
                  {courses.length === 0 && (
                    <p className="muted">No courses yet. Use Add Course to create one.</p>
                  )}
                  {courses.length > 0 && currentCourses.length === 0 && (
                    <p className="muted">
                      No courses in your current term. Pick a year below to see those
                      courses, or set your term in Settings.
                    </p>
                  )}
                  {currentCourses.length > 0 && <CourseList courses={currentCourses} />}
                </>
              )}
            </section>

            <YearCourses
              title="Past Courses"
              years={summary?.past_years ?? []}
              emptyMessage="Courses from earlier terms will appear here."
              selectedYear={selectedYear}
              onSelectYear={setSelectedYear}
            />

            <YearCourses
              title="Future Courses"
              years={summary?.future_years ?? []}
              emptyMessage="Courses you plan for later years will appear here."
              selectedYear={selectedYear}
              onSelectYear={setSelectedYear}
            />
          </div>

          <div className="gradesColumn">
            <SemesterSummary summary={summary} />

            {summary && (
              <CreditsBar
                completed={summary.credits_completed}
                inProgress={summary.credits_in_progress}
                target={summary.credit_target}
                required={summary.credits_required}
                elective={summary.credits_elective}
              />
            )}

            <GradeTrendChart points={summary?.term_history ?? []} />

            <AttentionPanel items={summary?.attention ?? []} userId={user?.id} />
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
