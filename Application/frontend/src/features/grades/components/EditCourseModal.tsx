import { useState, useEffect } from "react";
import EditCourseForm from "./EditCourseForm";
import { updateCourse } from "../api";
import { CourseCreate, CourseDetail, CourseUpdate, Semester } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";
import { getErrorMessage } from "./AddCourseModal";
import Modal from "../../../shared/components/Modal";

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
    professor: course?.professor ?? null,
    final_grade: course?.final_grade ?? 0,
    target_grade: course?.target_grade ?? null,
    category_weights: course?.category_weights ?? {},
    start_date: course?.start_date ?? null,
    end_date: course?.end_date ?? null,
    no_final: course?.no_final ?? false,
    transfer_credit: course?.transfer_credit ?? false,
    archived: course?.archived ?? false,
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
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal title="Edit Course" onClose={onClose}>
      <EditCourseForm
        form={form}
        updateField={(k, v) => setForm((s) => ({ ...s, [k]: v }))}
        onSubmit={handleSubmit}
        onCancel={onClose}
        submitting={loading}
        error={error}
      />
    </Modal>
  );
}