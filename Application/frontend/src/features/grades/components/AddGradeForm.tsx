import { GradeCreate } from "../types";
import ScheduleChoice from "./ScheduleChoice";
import BonusNote, { scoreInputClass } from "./BonusNote";

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
          id="grade-name"
          value={form.name}
          onChange={(event) => updateField("name", event.target.value)}
          className="--input mt-1 w-full rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white text-center"
          placeholder="Grade Name (e.g. Quiz 1)"
          aria-label="Grade name"
          required
        />
      </div>

      <div className="flex gap-3 justify-center">
        {/* Score is deliberately not `required`: a grade with no score yet is a
            supported state, and the placeholder says so. It carried `required`
            while this form was an inert <div>, where the attribute did nothing;
            now that the form is real, keeping it would break that behaviour. */}
        <input
          id="grade-score"
          type="number"
          step="any"
          min={0}
          // Number("") is 0, so clearing the box used to silently record a zero.
          value={form.score ?? ""}
          onChange={(event) =>
            updateField("score", event.target.value === "" ? null : Number(event.target.value))
          }
          className={scoreInputClass("--input mt-1 w-[45%] rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white text-center", form.score ?? null, form.max_score)}
          placeholder="Score (blank = not graded yet)"
          aria-label="Score, blank if not graded yet"
        />
        <input
          id="grade-max-score"
          type="number"
          step="any"
          min={0}
          value={form.max_score}
          onChange={(event) => updateField("max_score", Number(event.target.value))}
          className="--input mt-1 w-[45%] rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white text-center"
          placeholder="Max Score"
          aria-label="Max score"
          required
        />
      </div>

      <BonusNote score={form.score ?? null} maxScore={form.max_score} />

      {/* The date lives inside the choice: what it means is the decision, and
          the date is only one of the three answers. */}
      <ScheduleChoice
        dueDate={form.due_date}
        scheduleAs={form.schedule_as}
        onChange={(next) => {
          updateField("due_date", next.due_date);
          updateField("schedule_as", next.schedule_as);
        }}
        category={form.category}
        idPrefix="add-grade"
      />

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
          {submitting ? "Saving..." : "Add Grade"}
        </button>
      </div>
    </form>
  );
}
