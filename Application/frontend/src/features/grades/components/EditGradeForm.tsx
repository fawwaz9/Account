import { GradeCategory, GradeSchedule } from "../types";
import ScheduleChoice from "./ScheduleChoice";
import BonusNote, { scoreInputClass } from "./BonusNote";

/** The fields the edit-grade form holds. */
interface EditGradeFormState {
  name: string;
  /** Null while unmarked. */
  score: number | null;
  max_score: number;
  /** Null for no date. */
  due_date: string | null;
  /** "HH:MM"; null means no set time, not midnight. */
  due_time: string | null;
  /** Length of a calendar block; null for a task or an all-day block. */
  duration_minutes: number | null;
  /** Whether the date raises a task or a calendar block. */
  schedule_as: GradeSchedule;
  /** Dropped: kept on the course, out of every average. */
  excluded: boolean;
}

/** The grade's form state and setter, its category, its actions, and status text. */
interface EditGradeFormProps {
  readonly form: EditGradeFormState;
  /** Only words the calendar option for a midterm or a final. */
  readonly category: GradeCategory | null;
  readonly updateField: <K extends keyof EditGradeFormState>(key: K, value: EditGradeFormState[K]) => void;
  readonly onSubmit: () => void;
  readonly onCancel: () => void;
  readonly submitting: boolean;
  readonly error?: string | null;
}

/** The edit-grade form: name, score out of a maximum, the dropped toggle, and the date choice. */
export default function EditGradeForm({
  form,
  category,
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
          id="edit-grade-max-score"
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

      {/* For when a professor drops the two lowest quizzes. Deleting the grade
          would work too, but the mark happened and which ones are dropped
          changes as more work comes back, so it has to be reversible. */}
      <label className="dropGradeToggle">
        <input
          type="checkbox"
          checked={form.excluded}
          onChange={(event) => updateField("excluded", event.target.checked)}
        />
        <span>
          Don't count this toward the course
          <span className="dropGradeHint">
            Stays on the course, out of every average — for a mark your professor dropped.
          </span>
        </span>
      </label>

      <ScheduleChoice
        dueDate={form.due_date}
        dueTime={form.due_time}
        durationMinutes={form.duration_minutes}
        scheduleAs={form.schedule_as}
        onChange={(next) => {
          // All four together: the control clears what depends on what, and
          // applying them one at a time would put a half-cleared pair through
          // the validator on the way.
          updateField("due_date", next.due_date);
          updateField("due_time", next.due_time);
          updateField("duration_minutes", next.duration_minutes);
          updateField("schedule_as", next.schedule_as);
        }}
        category={category}
        idPrefix="edit-grade"
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
          {submitting ? "Saving..." : "Save Changes"}
        </button>
      </div>
    </form>
  );
}
