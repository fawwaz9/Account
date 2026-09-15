import { useState, useEffect } from "react";
import AddGradeForm from "./AddGradeForm";
import { createGrade } from "../api";
import { GradeCreate, GradeCategory, GradeSchedule } from "../types";
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
    // No deadline by default; the choice below only matters once there is one.
    due_date: null,
    // And no time of day even once there is a date: a guessed 09:00 reads on
    // the calendar as a fact rather than as a blank left unfilled.
    due_time: null,
    duration_minutes: null,
    // A midterm or a final is something you sit rather than tick off, so those
    // start on the calendar side and everything else starts as work to do.
    schedule_as:
      category === GradeCategory.MIDTERM || category === GradeCategory.FINAL
        ? GradeSchedule.EVENT
        : GradeSchedule.TASK,
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