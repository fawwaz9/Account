import { useState } from "react";
import AddCourseForm from "./AddCourseForm";
import { createCourse } from "../api";
import { CourseCreate, GradeCategory, Semester } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";

interface AddCourseModalProps {
  readonly open: boolean;
  readonly onClose: () => void;
  readonly onCourseAdded: () => void;
}

const defaultForm: CourseCreate = {
  code: "",
  name: "",
  semester: Semester.FALL,
  year: 1,
  credits: 3,
  required: true,
  professor: "",
  final_grade: 0,
  category_weights: {},
  start_date: null,
  end_date: null,
};

export default function AddCourseModal({
  open,
  onClose,
  onCourseAdded,
}: AddCourseModalProps) {
  const { user } = useAuth(); // moved to top level
  const [form, setForm] = useState(defaultForm);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function handleSubmit() {
    if (!user) return;

    setLoading(true);
    setError(null);
    try {
      // Fill any untouched categories with 0 before sending
      const fullWeights = Object.fromEntries(
        Object.values(GradeCategory).map((cat) => [
          cat,
          form.category_weights[cat] ?? 0,
        ])
      ) as Record<GradeCategory, number>;

      const payload = {
        code: form.code,
        name: form.name,
        semester: form.semester,
        year: form.year,
        credits: form.credits,
        required: form.required,
        professor: form.professor,
        final_grade: form.final_grade,
        category_weights: fullWeights,
        start_date: form.start_date || null,
        end_date: form.end_date || null,
      };
      await createCourse(user.id, payload);
      setForm(defaultForm);
      onCourseAdded();
      onClose();
    } catch (err: any) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="popup">
      <div className="addCoursePopup">
        <h2>Add Course</h2>
        <AddCourseForm
          form={form}
          updateField={(k, v) => setForm((s) => ({ ...s, [k]: v }))}
          onSubmit={handleSubmit}
          submitting={loading}
          error={error}
          onCancel={onClose}
          onReset={() => {
            setForm(defaultForm);
            setError(null);
          }}
        />
      </div>
    </div>
  );
}

export function getErrorMessage(apiError: unknown): string {
  // apiClient throws a plain Error whose message is already the unpacked
  // detail, so this has to come first -- JSON.stringify(new Error("x")) is "{}".
  if (apiError instanceof Error) {
    return apiError.message;
  }

  if (Array.isArray(apiError)) {
    return apiError
      .map((e: any) => e?.msg || e?.message || JSON.stringify(e))
      .join(", ");
  }

  if (typeof apiError === "object" && apiError !== null) {
    return JSON.stringify(apiError);
  }

  return typeof apiError === "string" && apiError
    ? apiError
    : "An unexpected error occurred.";
}