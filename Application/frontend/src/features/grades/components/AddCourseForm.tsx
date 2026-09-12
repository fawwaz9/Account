import {CourseCreate, GradeCategory, Semester } from "../types"
import CourseFlags from "./CourseFlags";

interface AddCourseFormProps {
  readonly form: CourseCreate;
  readonly updateField: <K extends keyof CourseCreate>(key: K, value: CourseCreate[K]) => void;
  readonly onSubmit: () => void;
  readonly onCancel: () => void;
  readonly onReset?: () => void;
  readonly submitting: boolean;
  readonly error?: string | null;
}

export default function AddCourseForm({
  form,
  updateField,
  onSubmit,
  onCancel,
  onReset,
  submitting,
  error,
}: AddCourseFormProps) {
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
      className="space-y-4 max-h-[74vh] overflow-y-auto pr-1 text-left"
      onSubmit={handleSubmit}
    >
      {/* Paired into rows. Nine single-field blocks in a 448px column was most
          of why this dialog always needed scrolling; .calField is
          `flex: 1 1 140px`, so these wrap to one per line on a narrow screen
          without a media query. */}
      <div className="calRow">
        <label className="calField">
          <span className="calFieldLabel">Course code</span>
          <input
            id="course-code"
            value={form.code}
            onChange={(event) => updateField("code", event.target.value)}
            className="--input w-full rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white"
            placeholder="COSC 121"
            required
          />
        </label>

        <label className="calField" style={{ flex: "2 1 220px" }}>
          <span className="calFieldLabel">Course name</span>
          <input
            id="course-name"
            value={form.name}
            onChange={(event) => updateField("name", event.target.value)}
            className="--input w-full rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white"
            placeholder="Computer Programming II"
            required
          />
        </label>
      </div>

      <div className="calRow">
        <label className="calField">
          <span className="calFieldLabel">Semester</span>
          <select
            id="course-semester"
            value={form.semester}
            onChange={(event) => updateField("semester", event.target.value as Semester)}
            className="--input w-full rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white"
            required
          >
            {Object.values(Semester).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>

        <label className="calField">
          <span className="calFieldLabel">Year</span>
          <input
            id="course-standing"
            type="number"
            min={1} max={10}
            value={form.year}
            onChange={(event) => updateField("year", Number(event.target.value))}
            className="--input w-full rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white"
            required
          />
        </label>

        <label className="calField">
          <span className="calFieldLabel">Credits</span>
          <input
            id="course-credits"
            type="number"
            min={0.5} max={10}
            step={0.5}
            value={form.credits}
            onChange={(event) => updateField("credits", Number(event.target.value))}
            className="--input w-full rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white"
            required
          />
        </label>
      </div>

      <div className="calRow">
        <label className="calField" style={{ flex: "2 1 200px" }}>
          <span className="calFieldLabel">Professor (optional)</span>
          <input
            id="course-professor"
            value={form.professor ?? ""}
            onChange={(event) => updateField("professor", event.target.value)}
            className="--input w-full rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white"
          />
        </label>

        <label className="calField">
          <span className="calFieldLabel">Final grade</span>
          <input
            id="course-final-grade"
            type="number"
            min={0}
            max={100}
            value={form.final_grade}
            onChange={(event) => updateField("final_grade", Number(event.target.value))}
            className="--input w-full rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white"
          />
        </label>

        <label className="calField">
          <span className="calFieldLabel">Target (blank = default)</span>
          <input
            id="course-target"
            type="number"
            min={0}
            max={100}
            value={form.target_grade ?? ""}
            onChange={(event) =>
              updateField("target_grade", event.target.value === "" ? null : Number(event.target.value))
            }
            className="--input w-full rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white"
          />
        </label>
      </div>

      <div className="calRow">
        <label className="calInlineField" style={{ flex: "0 0 auto" }}>
          <input
            id="required-checkbox"
            type="checkbox"
            checked={form.required}
            onChange={(event) => updateField("required", event.target.checked)}
            className="--input h-4 w-4 rounded border-slate-700 !bg-slate-900 !text-gold"
          />
          <span className="calFieldLabel">Required course</span>
        </label>
      </div>

      <div className="flex gap-3">
        <div>
          <label htmlFor="course-start-date" className="block text-sm text-slate-200">Starts</label>
          <input
            id="course-start-date"
            type="date"
            value={form.start_date ?? ""}
            onChange={(event) => updateField("start_date", event.target.value || null)}
            className="--input mt-1 rounded-lg border border-slate-700 bg-transparent text-white"
          />
        </div>
        <div>
          <label htmlFor="course-end-date" className="block text-sm text-slate-200">Ends</label>
          <input
            id="course-end-date"
            type="date"
            value={form.end_date ?? ""}
            onChange={(event) => updateField("end_date", event.target.value || null)}
            className="--input mt-1 rounded-lg border border-slate-700 bg-transparent text-white"
          />
        </div>
      </div>

      <CourseFlags form={form} updateField={updateField} idPrefix="add-course" />

      <div className="category_grid">
        {/* A real label per box, as EditCourseForm already does. The placeholder
            used to be the only thing naming these eight inputs, and it vanishes on
            the first keystroke -- leaving eight identical boxes with nothing to say
            which category each one weights, and eight bare spin buttons to a
            screen reader. */}
        {Object.values(GradeCategory).map((category) => (
          <div key={category} className="categoryWeightItem">
            <label htmlFor={`add-category-weight-${category}`} className="categoryWeightLabel">
              {category}
            </label>
            <input
              id={`add-category-weight-${category}`}
              type="number"
              className="categoryWeightInput"
              placeholder="0"
              min={0}
              max={100}
              value={form.category_weights?.[category] ?? ""}
              onChange={(e) => {
                const raw = e.target.value;
                updateField("category_weights", {
                  ...form.category_weights,
                  [category]: raw === "" ? undefined : Number(raw),
                });
              }}
            />
          </div>
        ))}
      </div>

      {error && (
        <div className="space-y-1">
          <p className="error">{error}</p>
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
          onClick={() => onReset? onReset(): null}
          className="rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-slate-200"
          disabled={submitting}
        >
          Reset
        </button>

        <button
          type="submit"
          className="rounded-lg !bg-gold !text-slate-950"
          disabled={submitting}
        >
          {submitting ? "Saving..." : "Add Course"}
        </button>
      </div>
    </form>
  );
}
