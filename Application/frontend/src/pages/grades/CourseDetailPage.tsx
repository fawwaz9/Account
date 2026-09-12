import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAuth } from "../../app/auth/AuthContext";
import { fetchCourseDetail, deleteCourse, deleteGrade } from "../../features/grades/api";
import { GradeCategory, Grade, CourseDetail } from "../../features/grades/types";
import { bonusLast, carriesBonus, isAdditive } from "../../features/grades/bonus";
import { trimNumber } from "../../shared/utils/numberUtils";
import GradeBand from "../../features/grades/components/GradeBand";
import CourseCost from "../../features/grades/components/CourseCost";
import AddGradeModal from "../../features/grades/components/AddGradeModal";
import EditGradeModal from "../../features/grades/components/EditGradeModal";
import EditCourseModal from "../../features/grades/components/EditCourseModal";
import DeleteConfirmModal from "../../features/grades/components/DeleteConfirmModal";
import RequiredFinalModal from "../../features/grades/components/RequiredFinalModal";
import BulkGradesModal from "../../features/grades/components/BulkGradesModal";
import { getErrorMessage } from "../../features/grades/components/AddCourseModal";
import GradeCategoryColumn from "../../features/grades/components/GradeCategoryColumn";
import ClassScheduleModal from "../../features/calender/components/ClassScheduleModal";
import "../../styles/calendar.css";


export default function CourseDetailPage() {
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [addGradeCategory, setAddGradeCategory] = useState<GradeCategory | null>(null);
  const [editGrade, setEditGrade] = useState<Grade | null>(null);
  const [editingCourse, setEditingCourse] = useState(false);
  const [showRequiredFinal, setShowRequiredFinal] = useState(false);
  const [showBulkAdd, setShowBulkAdd] = useState(false);
  const [showClassTimes, setShowClassTimes] = useState(false);

  const [deleteGradeTarget, setDeleteGradeTarget] = useState<Grade | null>(null);
  const [deletingGrade, setDeletingGrade] = useState(false);
  const [deleteGradeError, setDeleteGradeError] = useState<string | null>(null);

  const [deletingCourse, setDeletingCourse] = useState(false);
  const [confirmDeleteCourse, setConfirmDeleteCourse] = useState(false);
  const [deleteCourseError, setDeleteCourseError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function load() {
      if (!courseId || !user) {
        if (!courseId) navigate("/grades");
        return;
      }

      setLoading(true);
      setLoadError(null);
      try {
        const c = await fetchCourseDetail(user.id, courseId);
        if (mounted) setCourse(c);
      } catch (err) {
        // The message matters: a dropped connection or a 500 used to fall through
        // to "Course not found", telling you your course had been deleted when it
        // had not. The backend sends "Course not found" as its own 404 detail, so
        // the genuine case still reads correctly here.
        if (mounted) setLoadError(getErrorMessage(err));
      } finally {
        if (mounted) setLoading(false);
      }
    }

    load();
    return () => {
      mounted = false;
    };
  }, [courseId, user, navigate, reloadNonce]);

  const gradesByCategory = useMemo(() => {
    if (!course) return {} as Record<GradeCategory, Grade[]>;
    return course.grades.reduce((acc, grade) => {
      if (!acc[grade.category]) {
        acc[grade.category] = [];
      }
      acc[grade.category].push(grade);
      return acc;
    }, {} as Record<GradeCategory, Grade[]>);
  }, [course]);

  // Weighted categories, plus any category that actually holds grades. Filtering
  // on weight > 0 alone meant a grade under a zero-weight category had no column
  // to render in -- it stayed in the database, invisible and un-deletable.
  const weightedCategories = useMemo(() => {
    if (!course) return [];
    const weighted = Object.entries(course.category_weights)
      .filter(([, weight]) => weight > 0)
      .map(([category]) => category as GradeCategory);
    const withGrades = course.grades.map((grade) => grade.category);
    // Bonus reads as a footnote to the course rather than one of its parts, so
    // it sits after everything the course is actually marked out of.
    return bonusLast(
      [...new Set([...weighted, ...withGrades])].filter(
        (category) => category !== GradeCategory.FINAL
      )
    );
  }, [course]);

  const unweightedCategories = useMemo(() => {
    if (!course) return new Set<GradeCategory>();
    return new Set(
      weightedCategories.filter((category) => !(course.category_weights[category] ?? 0))
    );
  }, [course, weightedCategories]);

  const finalGrade = useMemo(
    () => course?.grades.find((g) => g.category === GradeCategory.FINAL) ?? null,
    [course]
  );

  function handleEditGrade(gradeId: string) {
    const grade = course?.grades.find((g) => g.id === gradeId) ?? null;
    setEditGrade(grade);
  }

  function handleAddGrade(category: GradeCategory) {
    setAddGradeCategory(category);
  }

  function handleFinalClick() {
    if (finalGrade) {
      setEditGrade(finalGrade);
    } else {
      setAddGradeCategory(GradeCategory.FINAL);
    }
  }

  function handleDeleteGradeRequest(grade: Grade) {
    setDeleteGradeError(null);
    setDeleteGradeTarget(grade);
  }

  async function handleConfirmDeleteGrade() {
    if (!courseId || !deleteGradeTarget || !user) return;

    setDeletingGrade(true);
    setDeleteGradeError(null);
    try {
      await deleteGrade(user.id, courseId, deleteGradeTarget.id);
      setDeleteGradeTarget(null);
      await refreshCourse();
    } catch (err: any) {
      setDeleteGradeError(getErrorMessage(err));
    } finally {
      setDeletingGrade(false);
    }
  }

  async function handleConfirmDeleteCourse() {
    if (!courseId || !user) return;

    setDeletingCourse(true);
    setDeleteCourseError(null);
    try {
      await deleteCourse(user.id, courseId);
      navigate("/grades");
    } catch (err: any) {
      setDeleteCourseError(getErrorMessage(err));
    } finally {
      setDeletingCourse(false);
    }
  }

  async function refreshCourse() {
    if (!courseId || !user) return;
    const c = await fetchCourseDetail(user.id, courseId);
    setCourse(c);
  }

  if (loading) return <div className="p-4">Loading...</div>;
  if (loadError) {
    return (
      <div className="p-4">
        <p className="loginError" role="alert">{loadError}</p>
        <button type="button" onClick={() => setReloadNonce((n) => n + 1)}>
          Try again
        </button>
      </div>
    );
  }
  if (!course || !courseId) return <div className="p-4">Course not found</div>;

  return (
    <div className="courseDetailPage">
      <button
        type="button"
        className="backButton"
        onClick={() => navigate(-1)}
        aria-label="Back"
      >
        &larr;
      </button>

      <h1 className="courseTitle">
        {course.code} - {course.name}
      </h1>

      <div className="summaryRow">
        <div className="summaryList">
          {Object.entries(course.category_weights)
            .filter(([, weight]) => weight > 0)
            .map(([category, weight]) => {
              // Straight from the API. Recomputing it here counted ungraded work
              // as a zero, so this strip disagreed with the average beside it.
              const average = course.category_averages?.[category as GradeCategory] ?? 0;
              // Trimmed rather than padded: most of these are whole numbers,
              // and "18.00/20" spent two characters saying nothing.
              const weightage = trimNumber((weight * average) / 100);
              // An additive category is not marks out of a total, so showing it
              // as "2.50/5" read as three marks lost. It is points gained.
              const additive = isAdditive(category);
              return (
                <div
                  className={additive ? "summaryItem summaryItemBonus" : "summaryItem"}
                  key={category}
                >
                  <span style={{ textTransform: "capitalize" }}>{category}</span>
                  <span>
                    {additive
                      ? `+${weightage}`
                      : `${weightage}/${trimNumber(weight)}`}
                  </span>
                </div>
              );
            })}
        </div>

        <div className="averageSection">
          <div className="averageLabel"> Average</div>
          <div className="courseAverageCircle">{course.average}</div>
          {course.letter_grade && (
            <div className="courseGradePoints">
              {course.letter_grade} &middot; {course.grade_points.toFixed(2)}
            </div>
          )}
          {/* The average itself stays the capped number. This only says that
              bonus is in play, by either route -- a weighted bonus category or
              an ordinary grade marked above its own maximum. */}
          {carriesBonus(course) && (
            <div className="bonusBadge" title="Bonus marks count toward this course">
              ★ carries bonus
            </div>
          )}
        </div>
      </div>

      {/* Under the average, because it is the same number with its uncertainty
          still attached. Hides itself once nothing is outstanding. */}
      {/* Cost on the left, the band on the right. Both hide themselves when
          they have nothing to say, so the row collapses rather than leaving a
          gap -- see .courseInsights:empty. */}
      {user && courseId && (
        <div className="courseInsights">
          <CourseCost userId={user.id} courseId={courseId} nonce={reloadNonce} />
          <GradeBand userId={user.id} courseId={courseId} nonce={reloadNonce} />
        </div>
      )}

      <div className="categoriesGrid">
        {weightedCategories.map((category) => (
          <GradeCategoryColumn
            key={category}
            title={unweightedCategories.has(category) ? `${category} (0% weight)` : category}
            category={category}
            items={gradesByCategory[category] ?? []}
            onEditItem={handleEditGrade}
            onAddGrade={handleAddGrade}
            onDeleteItem={handleDeleteGradeRequest}
          />
        ))}
      </div>

      <div className="finalGradeActions">
        <button
          type="button"
          className="finalGradeButton"
          onClick={handleFinalClick}
        >
          {finalGrade ? `Final: ${finalGrade.score ?? "-"}/${finalGrade.max_score}` : "Add Final Grade"}
        </button>

        <button
          type="button"
          className="requiredFinalButton"
          onClick={() => setShowRequiredFinal(true)}
        >
          Required Final Grade
        </button>
      </div>

      <div className="flex gap-3">
        <button
          type="button"
          className="editCourseButton"
          onClick={() => setShowBulkAdd(true)}
        >
          Add Several
        </button>

        <button
          type="button"
          className="editCourseButton"
          onClick={() => setShowClassTimes(true)}
        >
          Class Times
        </button>

        <button
          type="button"
          className="editCourseButton"
          onClick={() => setEditingCourse(true)}
        >
          Edit Course
        </button>

        <button
          type="button"
          className="deleteCourseButton"
          onClick={() => {
            setDeleteCourseError(null);
            setConfirmDeleteCourse(true);
          }}
        >
          Delete Course
        </button>
      </div>

      <AddGradeModal
        open={addGradeCategory !== null}
        courseId={courseId}
        category={addGradeCategory}
        onClose={() => setAddGradeCategory(null)}
        onGradeAdded={refreshCourse}
      />

      <EditGradeModal
        open={editGrade !== null}
        courseId={courseId}
        grade={editGrade}
        onClose={() => setEditGrade(null)}
        onGradeUpdated={refreshCourse}
        onGradeDeleted={refreshCourse}
      />

      <EditCourseModal
        open={editingCourse}
        course={course}
        onClose={() => setEditingCourse(false)}
        onCourseUpdated={refreshCourse}
      />

      <ClassScheduleModal
        open={showClassTimes}
        courseId={courseId}
        courseCode={course.code}
        startDate={course.start_date}
        endDate={course.end_date}
        onClose={() => setShowClassTimes(false)}
        onSaved={refreshCourse}
      />

      <BulkGradesModal
        open={showBulkAdd}
        courseId={courseId}
        onClose={() => setShowBulkAdd(false)}
        onGradesAdded={refreshCourse}
      />

      <RequiredFinalModal
        open={showRequiredFinal}
        courseId={courseId}
        courseCode={course.code}
        onClose={() => setShowRequiredFinal(false)}
      />

      <DeleteConfirmModal
        open={deleteGradeTarget !== null}
        title="Delete Grade"
        message={`Are you sure you want to delete "${deleteGradeTarget?.name}"? This cannot be undone.`}
        onConfirm={handleConfirmDeleteGrade}
        onCancel={() => setDeleteGradeTarget(null)}
        submitting={deletingGrade}
        error={deleteGradeError}
      />

      <DeleteConfirmModal
        open={confirmDeleteCourse}
        title="Delete Course"
        message={`Are you sure you want to delete "${course.code} - ${course.name}"? This will permanently delete all grades in this course.`}
        onConfirm={handleConfirmDeleteCourse}
        onCancel={() => setConfirmDeleteCourse(false)}
        submitting={deletingCourse}
        error={deleteCourseError}
      />
    </div>
  );
}