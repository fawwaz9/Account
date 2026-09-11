interface EditGradeFormState {
  name: string;
  /** null while the work has not been marked */
  score: number | null;
  max_score: number;
  /** null for an assignment with no deadline */
  due_date: string | null;
}

interface EditGradeFormProps {
  readonly form: EditGradeFormState;
  readonly updateField: <K extends keyof EditGradeFormState>(key: K, value: EditGradeFormState[K]) => void;
  readonly onSubmit: () => void;
  readonly onCancel: () => void;
  readonly submitting: boolean;
  readonly error?: string | null;
}

export default function EditGradeForm({
  form,
  updateField,
  onSubmit,
  onCancel,
  submitting,
  error,
}: EditGradeFormProps) {
  // A real <form>, so the `required` attributes below actually run. These were
  // <div>s with a type="button" submit, which meant no constraint validation ever
  // fired and Enter-to-submit was dead -- a blank submit went to the server and
  // came back as an error message at the bottom of the dialog.
  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    onSubmit();
  }

  return (
    <form
      className="space-y-4 max-h-[70vh] overflow-y-auto pr-1 text-center"
      onSubmit={handleSubmit}
    >
      <div>
        <input
          id="edit-grade-name"
          value={form.name}
          onChange={(event) => updateField("name", event.target.value)}
          className="--input mt-1 w-full rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white text-center"
          placeholder="Grade Name"
          aria-label="Grade name"
          required
        />
      </div>

      <div className="flex gap-3 justify-center">
        {/* Not `required`, same as AddGradeForm: clearing a score back to
            "not graded yet" is a supported edit, and matters more here than on
            the add form. */}
        <input
          id="edit-grade-score"
          type="number"
          min={0}
          // Number("") is 0, so clearing the box used to silently record a zero.
          value={form.score ?? ""}
          onChange={(event) =>
            updateField("score", event.target.value === "" ? null : Number(event.target.value))
          }
          className="--input mt-1 w-[45%] rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white text-center"
          placeholder="Score (blank = not graded yet)"
          aria-label="Score, blank if not graded yet"
        />
        <input
          id="edit-grade-max-score"
          type="number"
          min={0}
          value={form.max_score}
          onChange={(event) => updateField("max_score", Number(event.target.value))}
          className="--input mt-1 w-[45%] rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white text-center"
          placeholder="Max Score"
          aria-label="Max score"
          required
        />
      </div>

      <div>
        <label htmlFor="edit-grade-due-date" className="block text-sm text-slate-200">
          Due date (optional — setting one adds it to your tasks and calendar)
        </label>
        <input
          id="edit-grade-due-date"
          type="date"
          value={form.due_date ?? ""}
          onChange={(event) => updateField("due_date", event.target.value || null)}
          className="--input mt-1 w-full rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white text-center"
        />
      </div>

      {error && (
        <div className="space-y-1">
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      <div className="flex justify-end gap-3 pt-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-slate-700 !bg-slate-900 !text-slate-200"
          disabled={submitting}
        >
          Cancel
        </button>
        <button
          type="submit"
          className="rounded-lg !bg-gold !text-slate-950"
          disabled={submitting}
        >
          {submitting ? "Saving..." : "Save Changes"}
        </button>
      </div>
    </form>
  );
}
