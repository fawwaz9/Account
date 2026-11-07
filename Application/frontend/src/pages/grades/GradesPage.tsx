import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import CourseList from "../../features/grades/components/CourseList";
import AddCourseModal, { getErrorMessage } from "../../features/grades/components/AddCourseModal";
import EditCourseModal from "../../features/grades/components/EditCourseModal";
import DeleteConfirmModal from "../../features/grades/components/DeleteConfirmModal";
import PastCoursesEntry from "../../features/grades/components/PastCoursesEntry";
import { deleteCourse } from "../../features/grades/api";
import SyllabusModal from "../../features/intake/SyllabusModal";
import { intakeStatus } from "../../features/intake/api";
import CourseSearch from "../../features/grades/components/CourseSearch";
import SemesterSummary from "../../features/grades/components/SemesterSummary";
import CreditsBar from "../../features/grades/components/CreditsBar";
import YearCourses from "../../features/grades/components/YearCourses";
import AttentionPanel from "../../features/grades/components/AttentionPanel";
import BlindSpotsPanel from "../../features/grades/components/BlindSpotsPanel";
import GradeTrendChart from "../../features/grades/components/GradeTrendChart";
import TermReviewPanel from "../../features/grades/components/TermReviewPanel";
import { useCourses } from "../../features/grades/hooks/useCourses";
import { useDashboard } from "../../features/grades/hooks/useDashboard";
import { useBlindSpots } from "../../features/grades/hooks/useBlindSpots";
import { Course } from "../../features/grades/types";
import { useAuth } from "../../app/auth/AuthContext";
import { useShortcut } from "../../shared/hooks/useShortcut";

/** One term's courses within a selected school year. */
interface TermGroup {
  semester: string;
  courses: Course[];
}

/**
 * The grades page: current-term courses (or a chosen year's, by term), search and add, past
 * courses with quick entry of final-grade-only ones, beside the dashboard column of averages,
 * credits, trend, term reviews, Attention and blind spots.
 */
export default function GradesPage() {
  const { courses, loading, error, reload } = useCourses();
  const { summary, reload: reloadSummary } = useDashboard();
  const { spots } = useBlindSpots();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const { user } = useAuth();
  const navigate = useNavigate();
  const [readingSyllabus, setReadingSyllabus] = useState(false);
  // A final-grade-only course has no page; its card opens Edit Course here instead.
  const [editingFinalOnly, setEditingFinalOnly] = useState<Course | null>(null);
  const [deletingFinalOnly, setDeletingFinalOnly] = useState<Course | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  // Offered only once the server says it can read one: a button that always
  // answers "not set up yet" is a control that only states an absence.
  const [syllabusReady, setSyllabusReady] = useState(false);
  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    intakeStatus(user.id)
      .then((status) => { if (!cancelled) setSyllabusReady(status.available); })
      .catch(() => { if (!cancelled) setSyllabusReady(false); });
    return () => { cancelled = true; };
  }, [user?.id]);

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

  async function confirmDeleteFinalOnly() {
    if (!user || !deletingFinalOnly) return;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await deleteCourse(user.id, deletingFinalOnly.id);
      setDeletingFinalOnly(null);
      handleCourseAdded();
    } catch (err) {
      setDeleteError(getErrorMessage(err));
    } finally {
      setDeleteBusy(false);
    }
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
                  <span className="addCourseActions">
                    <button
                      type="button"
                      className="buttons addCourseButton"
                      onClick={() => setIsModalOpen(true)}
                    >
                      Add Course
                    </button>
                    {syllabusReady && (
                      <button
                        type="button"
                        className="buttons addCourseButton"
                        onClick={() => setReadingSyllabus(true)}
                      >
                        From a syllabus
                      </button>
                    )}
                  </span>
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
                      <CourseList courses={group.courses} onEditFinalOnly={(picked) => setEditingFinalOnly(picked)} />
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
                  {currentCourses.length > 0 && (
                    <CourseList courses={currentCourses} onEditFinalOnly={(picked) => setEditingFinalOnly(picked)} />
                  )}
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
            {/* Under past courses (owner, 2026-11-07): courses you have only a final grade for. */}
            {user && (
              <div className="pastCoursesEntry">
                <PastCoursesEntry userId={user.id} onAdded={handleCourseAdded} />
              </div>
            )}

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

            <div className="gradesLinks">
              <Link to="/grades/degree" className="calButton degreeLink">Degree audit</Link>
              {/* Phase 4 item 12. */}
              <Link to="/grades/next-term" className="calButton degreeLink">Plan next term</Link>
            </div>

            <GradeTrendChart points={summary?.term_history ?? []} />

            {/* Phase 2 item 13: silent unless a course finished recently. */}
            {user && <TermReviewPanel userId={user.id} />}

            <AttentionPanel items={summary?.attention ?? []} userId={user?.id} />

            <BlindSpotsPanel spots={spots} />
          </div>
        </div>
      </div>

      {readingSyllabus && user && (
        <SyllabusModal
          userId={user.id}
          onClose={() => setReadingSyllabus(false)}
          onBuilt={(courseId) => {
            setReadingSyllabus(false);
            void reload();
            navigate(`/grades/courses/${courseId}`);
          }}
        />
      )}

      <AddCourseModal
        open={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onCourseAdded={handleCourseAdded}
      />

      <EditCourseModal
        open={editingFinalOnly !== null}
        course={editingFinalOnly}
        onClose={() => setEditingFinalOnly(null)}
        onCourseUpdated={handleCourseAdded}
        onDelete={() => {
          setDeleteError(null);
          setDeletingFinalOnly(editingFinalOnly);
          setEditingFinalOnly(null);
        }}
      />

      <DeleteConfirmModal
        open={deletingFinalOnly !== null}
        title="Delete Course"
        message={`Delete "${deletingFinalOnly?.code} - ${deletingFinalOnly?.name}"? Its final grade leaves your averages and credits.`}
        onConfirm={() => void confirmDeleteFinalOnly()}
        onCancel={() => setDeletingFinalOnly(null)}
        submitting={deleteBusy}
        error={deleteError}
      />
    </>
  );
}
