import { GradeCreate } from "../types";

interface AddGradeFormProps {
  readonly form: GradeCreate;
  readonly updateField: <K extends keyof GradeCreate>(key: K, value: GradeCreate[K]) => void;
  readonly onSubmit: () => void;
  readonly onCancel: () => void;
  readonly submitting: boolean;
  readonly error?: string | null;
}

export default function AddGradeForm({
  form,
  updateField,
  onSubmit,
  onCancel,
  submitting,
  error,
}: AddGradeFormProps) {
  return (
    <div className="space-y-4 max-h-[70vh] overflow-y-auto pr-1 text-center">
      <div>
        <input
          id="grade-name"
          value={form.name}
          onChange={(event) => updateField("name", event.target.value)}
          className="--input mt-1 w-full rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white text-center"
          placeholder="Grade Name (e.g. Quiz 1)"
          required
        />
      </div>

      <div className="flex gap-3 justify-center">
        <input
          id="grade-score"
          type="number"
          min={0}
          value={form.score}
          onChange={(event) => updateField("score", Number(event.target.value))}
          className="--input mt-1 w-[45%] rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white text-center"
          placeholder="Score"
          required
        />
        <input
          id="grade-max-score"
          type="number"
          min={0}
          value={form.max_score}
          onChange={(event) => updateField("max_score", Number(event.target.value))}
          className="--input mt-1 w-[45%] rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white text-center"
          placeholder="Max Score"
          required
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
          type="button"
          onClick={() => onSubmit()}
          className="rounded-lg !bg-gold !text-slate-950"
          disabled={submitting}
        >
          {submitting ? "Saving..." : "Add Grade"}
        </button>
      </div>
    </div>
  );
}