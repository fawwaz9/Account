import { useState } from "react";
import AddCourseForm from "./AddCourseForm";
import { createCourse } from "../api";
import { CourseCreate, GradeCategory, Semester } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";
import Modal from "../../../shared/components/Modal";

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
  professor: null,
  section: null,
  final_grade: 0,
  target_grade: null,
  category_weights: {},
  start_date: null,
  end_date: null,
  no_final: false,
  transfer_credit: false,
  archived: false,
  links: [],
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
        section: form.section?.trim() || null,
        final_grade: form.final_grade,
        target_grade: form.target_grade,
        category_weights: fullWeights,
        start_date: form.start_date || null,
        end_date: form.end_date || null,
        no_final: form.no_final,
        transfer_credit: form.transfer_credit,
        archived: form.archived,
        // Added from the course page once it exists, not on the way in.
        links: [],
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
    <Modal title="Add Course" onClose={onClose} panelClassName="widePopup">
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
    </Modal>
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