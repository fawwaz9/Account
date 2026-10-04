import { useMemo, useState } from "react";
import CourseList from "../../features/grades/components/CourseList";
import AddCourseModal from "../../features/grades/components/AddCourseModal";
import CourseSearch from "../../features/grades/components/CourseSearch";
import SemesterSummary from "../../features/grades/components/SemesterSummary";
import CreditsBar from "../../features/grades/components/CreditsBar";
import YearCourses from "../../features/grades/components/YearCourses";
import AttentionPanel from "../../features/grades/components/AttentionPanel";
import BlindSpotsPanel from "../../features/grades/components/BlindSpotsPanel";
import GradeTrendChart from "../../features/grades/components/GradeTrendChart";
import { useCourses } from "../../features/grades/hooks/useCourses";
import { useDashboard } from "../../features/grades/hooks/useDashboard";
import { useBlindSpots } from "../../features/grades/hooks/useBlindSpots";
import { Course } from "../../features/grades/types";
import { useAuth } from "../../app/auth/AuthContext";
import { useShortcut } from "../../shared/hooks/useShortcut";

interface TermGroup {
  semester: string;
  courses: Course[];
}

export default function GradesPage() {
  const { courses, loading, error, reload } = useCourses();
  const { summary, reload: reloadSummary } = useDashboard();
  const { spots } = useBlindSpots();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const { user } = useAuth();

  // Archived means "done with, keep the record": it still counts toward the
  // average and stays searchable, it just should not crowd the lists you read
  // every day. Filtered once here so the current term, the year groups and the
  // empty-state copy all agree about what is on screen.
  const archivedCount = useMemo(
    () => courses.filter((course) => course.archived).length,
    [courses]
  );

  const visibleCourses = useMemo(
    () => (showArchived ? courses : courses.filter((course) => !course.archived)),
    [courses, showArchived]
  );

  // The default list is the current term only. Everything else is reached
  // through a year card or the search box, which spans every term.
  const currentCourses = useMemo(
    () => visibleCourses.filter((course) => course.term_bucket === "current"),
    [visibleCourses]
  );

  // The API returns courses sorted by year, then term order, then code, so
  // consecutive runs are already the term groups -- no need for the client to
  // know what follows Fall.
  const selectedTerms = useMemo<TermGroup[]>(() => {
    if (selectedYear === null) return [];

    const groups: TermGroup[] = [];
    for (const course of visibleCourses) {
      if (course.year !== selectedYear) continue;

      const last = groups[groups.length - 1];
      if (last && last.semester === course.semester) {
        last.courses.push(course);
      } else {
        groups.push({ semester: course.semester, courses: [course] });
      }
    }
    return groups;
  }, [visibleCourses, selectedYear]);

  function handleCourseAdded() {
    reload();
    reloadSummary();
  }

  const viewingYear = selectedYear !== null;

  // Only while "Add Course" is on screen: a past year's view has no such button.
  useShortcut("n", () => setIsModalOpen(true), !viewingYear);

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
                  <span className="no-print sectionHeadingActions">
                    {/* Only offered on a specific year: "the current term"
                        moves, so it is not the record worth keeping that a
                        past year already is. */}
                    <button
                      type="button"
                      className="buttons addCourseButton"
                      onClick={() => window.print()}
                    >
                      Print this year
                    </button>
                    <button
                      type="button"
                      className="buttons addCourseButton"
                      onClick={() => setSelectedYear(null)}
                    >
                      Current Courses
                    </button>
                  </span>
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

              {/* Offered only when archived courses exist. A permanent switch
                  for a state most people never use is just another control to
                  read past. */}
              {archivedCount > 0 && (
                <button
                  type="button"
                  className="archivedToggle"
                  onClick={() => setShowArchived((shown) => !shown)}
                  aria-pressed={showArchived}
                >
                  {showArchived
                    ? `Hide archived (${archivedCount})`
                    : `Show archived (${archivedCount})`}
                </button>
              )}

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
                  {visibleCourses.length === 0 && (
                    <p className="muted">No courses yet. Use Add Course to create one.</p>
                  )}
                  {visibleCourses.length > 0 && currentCourses.length === 0 && (
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

            <BlindSpotsPanel spots={spots} />
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
