import { useState, useEffect } from "react";
import EditGradeForm from "./EditGradeForm";
import DeleteConfirmModal from "./DeleteConfirmModal";
import { updateGrade, deleteGrade } from "../api";
import { Grade, GradeUpdate } from "../types";
import { useAuth } from "../../../app/auth/AuthContext";
import { getErrorMessage } from "./AddCourseModal";
import Modal from "../../../shared/components/Modal";

interface EditGradeModalProps {
  readonly open: boolean;
  readonly courseId: string;
  readonly grade: Grade | null;
  readonly onClose: () => void;
  readonly onGradeUpdated: () => void;
  readonly onGradeDeleted: () => void;
}

function buildFormFromGrade(grade: Grade | null) {
  return {
    name: grade?.name ?? "",
    score: grade?.score ?? null,
    max_score: grade?.max_score ?? 0,
    due_date: grade?.due_date ?? null,
  };
}

export default function EditGradeModal({
  open,
  courseId,
  grade,
  onClose,
  onGradeUpdated,
  onGradeDeleted,
}: EditGradeModalProps) {
  const { user } = useAuth();
  const [form, setForm] = useState(buildFormFromGrade(grade));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    setForm(buildFormFromGrade(grade));
    setError(null);
    setConfirmingDelete(false);
    setDeleteError(null);
  }, [grade, open]);

  if (!open || !grade) return null;

  async function handleSubmit() {
    if (!grade || !user) return;

    setLoading(true);
    setError(null);
    try {
      const payload: Partial<GradeUpdate> = {
        name: form.name,
        score: form.score,
        max_score: form.max_score,
        // Clearing this removes the task it raised; setting it moves the task.
        due_date: form.due_date,
      };
      await updateGrade(user.id, courseId, grade.id, payload);
      onGradeUpdated();
      onClose();
    } catch (err: any) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirmDelete() {
    if (!grade || !user) return;

    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteGrade(user.id, courseId, grade.id);
      setConfirmingDelete(false);
      onGradeDeleted();
      onClose();
    } catch (err: any) {
      setDeleteError(getErrorMessage(err));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      <Modal title={`Edit ${grade.category} Grade`} onClose={onClose}>
        <EditGradeForm
          form={form}
          updateField={(k, v) => setForm((s) => ({ ...s, [k]: v }))}
          onSubmit={handleSubmit}
          onCancel={onClose}
          submitting={loading}
          error={error}
        />

        <div className="flex justify-center pt-2">
          <button
            type="button"
            className="deleteGradeLinkButton"
            onClick={() => setConfirmingDelete(true)}
            disabled={loading}
          >
            Delete this grade
          </button>
        </div>
      </Modal>

      <DeleteConfirmModal
        open={confirmingDelete}
        title="Delete Grade"
        message={`Are you sure you want to delete "${grade.name}"? This cannot be undone.`}
        onConfirm={handleConfirmDelete}
        onCancel={() => setConfirmingDelete(false)}
        submitting={deleting}
        error={deleteError}
      />
    </>
  );
}