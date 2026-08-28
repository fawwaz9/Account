import { useState, useEffect } from "react";
import EditCourseForm from "./EditCourseForm";
import { updateCourse } from "../api";
import { CourseCreate, CourseDetail, CourseUpdate, Semester } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";
import { getErrorMessage } from "./AddCourseModal";

interface EditCourseModalProps {
  readonly open: boolean;
  readonly course: CourseDetail | null;
  readonly onClose: () => void;
  readonly onCourseUpdated: () => void;
}

function buildFormFromCourse(course: CourseDetail | null): CourseCreate {
  return {
    code: course?.code ?? "",
    name: course?.name ?? "",
    semester: course?.semester ?? Semester.FALL,
    year: course?.year ?? 1,
    credits: course?.credits ?? 3,
    required: course?.required ?? true,
    professor: course?.professor ?? "",
    final_grade: course?.final_grade ?? 0,
    category_weights: course?.category_weights ?? {},
  };
}

export default function EditCourseModal({
  open,
  course,
  onClose,
  onCourseUpdated,
}: EditCourseModalProps) {
  const { user } = useAuth();
  const [form, setForm] = useState<CourseCreate>(buildFormFromCourse(course));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setForm(buildFormFromCourse(course));
    setError(null);
  }, [course, open]);

  if (!open || !course) return null;

  async function handleSubmit() {
    if (!course || !user) return;

    setLoading(true);
    setError(null);
    try {
      const payload: Partial<CourseUpdate> = { ...form };
      await updateCourse(user.id, course.id, payload);
      onCourseUpdated();
      onClose();
    } catch (err: any) {
      const apiError =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        err?.message;
      setError(getErrorMessage(apiError));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="popup">
      <div className="addCoursePopup">
        <h2>Edit Course</h2>
        <EditCourseForm
          form={form}
          updateField={(k, v) => setForm((s) => ({ ...s, [k]: v }))}
          onSubmit={handleSubmit}
          onCancel={onClose}
          submitting={loading}
          error={error}
        />
      </div>
    </div>
  );
}