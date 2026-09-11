import { useState, useEffect } from "react";
import AddGradeForm from "./AddGradeForm";
import { createGrade } from "../api";
import { GradeCreate, GradeCategory } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";
import { getErrorMessage } from "./AddCourseModal";
import Modal from "../../../shared/components/Modal";

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
    // null, not 0: a new assignment is unmarked until it is marked, and a 0
    // would drag the category average down as though it had been failed.
    score: null,
    max_score: 0,
    category: category ?? GradeCategory.OTHER,
    // No deadline by default. Setting one raises a task for the assignment,
    // which closes itself when the score lands.
    due_date: null,
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
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal title={`Add Grade — ${category}`} onClose={onClose}>
      <AddGradeForm
        form={form}
        updateField={(k, v) => setForm((s) => ({ ...s, [k]: v }))}
        onSubmit={handleSubmit}
        submitting={loading}
        error={error}
        onCancel={onClose}
      />
    </Modal>
  );
}