import { useState, useEffect } from "react";
import AddGradeForm from "./AddGradeForm";
import { createGrade } from "../api";
import { GradeCreate, GradeCategory } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";
import { getErrorMessage } from "./AddCourseModal";

interface AddGradeModalProps {
  readonly open: boolean;
  readonly courseId: string;
  readonly category: GradeCategory | null;
  readonly onClose: () => void;
  readonly onGradeAdded: () => void;
}

function buildDefaultForm(category: GradeCategory | null): GradeCreate {
  return {
    name: "",
    score: 0,
    max_score: 0,
    category: category ?? GradeCategory.OTHER,
  };
}

export default function AddGradeModal({
  open,
  courseId,
  category,
  onClose,
  onGradeAdded,
}: AddGradeModalProps) {
  const { user } = useAuth();
  const [form, setForm] = useState<GradeCreate>(buildDefaultForm(category));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setForm(buildDefaultForm(category));
    setError(null);
  }, [category, open]);

  if (!open || !category) return null;

  async function handleSubmit() {
    if (!user) return;

    setLoading(true);
    setError(null);
    try {
      await createGrade(user.id, courseId, form);
      onGradeAdded();
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
        <h2>Add Grade — {category}</h2>
        <AddGradeForm
          form={form}
          updateField={(k, v) => setForm((s) => ({ ...s, [k]: v }))}
          onSubmit={handleSubmit}
          submitting={loading}
          error={error}
          onCancel={onClose}
        />
      </div>
    </div>
  );
}