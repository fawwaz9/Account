import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAuth } from "../../app/auth/AuthContext";
import { fetchCourseDetail, deleteCourse, deleteGrade } from "../../features/grades/api";
import { GradeCategory, Grade, CourseDetail } from "../../features/grades/types";
import AddGradeModal from "../../features/grades/components/AddGradeModal";
import EditGradeModal from "../../features/grades/components/EditGradeModal";
import EditCourseModal from "../../features/grades/components/EditCourseModal";
import DeleteConfirmModal from "../../features/grades/components/DeleteConfirmModal";
import { getErrorMessage } from "../../features/grades/components/AddCourseModal";
import GradeCategoryColumn from "../../features/grades/components/GradeCategoryColumn";


export default function CourseDetailPage() {
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [addGradeCategory, setAddGradeCategory] = useState<GradeCategory | null>(null);
  const [editGrade, setEditGrade] = useState<Grade | null>(null);
  const [editingCourse, setEditingCourse] = useState(false);

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
      try {
        const c = await fetchCourseDetail(user.id, courseId);
        if (mounted) setCourse(c);
      } catch (err) {
        console.error(err);
      } finally {
        if (mounted) setLoading(false);
      }
    }

    load();
    return () => {
      mounted = false;
    };
  }, [courseId, user, navigate]);

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

  const weightedCategories = useMemo(() => {
    if (!course) return [];
    return Object.entries(course.category_weights)
      .filter(([category, weight]) => weight > 0 && category !== GradeCategory.FINAL)
      .map(([category]) => category as GradeCategory);
  }, [course]);

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
      const apiError =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        err?.message;
      setDeleteGradeError(getErrorMessage(apiError));
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
      const apiError =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        err?.message;
      setDeleteCourseError(getErrorMessage(apiError));
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
              const items = gradesByCategory[category as GradeCategory] ?? [];
              const earned = items.reduce((sum, g) => sum + (g.score ?? 0), 0);
              const possible = items.reduce((sum, g) => sum + g.max_score, 0);
              const weightage = (weight * (earned / (possible || 1))).toFixed(2);
              return (
                <div className="summaryItem" key={category}>
                  <span style={{ textTransform: "capitalize" }}>{category}</span>
                  <span>
                    {weightage}/{weight}
                  </span>
                </div>
              );
            })}
        </div>

        <div className="averageSection">
          <div className="averageLabel"> Average</div>
          <div className="courseAverageCircle">{course.average}</div>
        </div>
      </div>

      <div className="categoriesGrid">
        {weightedCategories.map((category) => (
          <GradeCategoryColumn
            key={category}
            title={category}
            category={category}
            items={gradesByCategory[category] ?? []}
            onEditItem={handleEditGrade}
            onAddGrade={handleAddGrade}
            onDeleteItem={handleDeleteGradeRequest}
          />
        ))}
      </div>

      <button
        type="button"
        className="finalGradeButton"
        onClick={handleFinalClick}
      >
        {finalGrade ? `Final: ${finalGrade.score}/${finalGrade.max_score}` : "Add Final Grade"}
      </button>

      <div className="flex gap-3">
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