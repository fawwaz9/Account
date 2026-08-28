import { CourseCreate, GradeCategory, Semester } from "../types";

interface EditCourseFormProps {
  readonly form: CourseCreate;
  readonly updateField: <K extends keyof CourseCreate>(key: K, value: CourseCreate[K]) => void;
  readonly onSubmit: () => void;
  readonly onCancel: () => void;
  readonly submitting: boolean;
  readonly error?: string | null;
}

export default function EditCourseForm({
  form,
  updateField,
  onSubmit,
  onCancel,
  submitting,
  error,
}: EditCourseFormProps) {
  return (
    <div className="space-y-4 max-h-[70vh] overflow-y-auto pr-1 text-center">
      <div>
        <input
          id="edit-course-code"
          value={form.code}
          onChange={(event) => updateField("code", event.target.value)}
          className="--input mt-1 w-[30%] rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white text-center"
          placeholder="Course Code"
          required
        />
      </div>

      <div>
        <input
          id="edit-course-name"
          value={form.name}
          onChange={(event) => updateField("name", event.target.value)}
          className="--input mt-1 w-[60%] rounded-lg border border-slate-700 bg-transparent px-3 py-2 text-white"
          placeholder="Course Name"
          required
        />
      </div>

      <div>
        <label htmlFor="edit-course-semester" className="block text-sm text-slate-200">Semester</label>
        <select
          id="edit-course-semester"
          value={form.semester}
          onChange={(event) => updateField("semester", event.target.value as Semester)}
          className="--select mt-1 w-full rounded-lg border border-slate-700 bg-transparent text-white"
          required
        >
          {Object.values(Semester).map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="edit-course-standing" className="block text-sm text-slate-200">Year</label>
        <input
          id="edit-course-standing"
          type="number"
          min={1} max={10}
          value={form.year}
          onChange={(event) => updateField("year", Number(event.target.value))}
          className="--input mt-1 w-full rounded-lg border border-slate-700 bg-transparent text-white"
          required
        />
      </div>

      <div>
        <label htmlFor="edit-course-credits" className="block text-sm text-slate-200">Credits</label>
        <input
          id="edit-course-credits"
          type="number"
          min={0.5} max={10}
          step={0.5}
          value={form.credits}
          onChange={(event) => updateField("credits", Number(event.target.value))}
          className="--input mt-1 w-full rounded-lg border border-slate-700 bg-transparent text-white"
          required
        />
      </div>

      <div>
        <label htmlFor="edit-course-final-grade" className="block text-sm text-slate-200">Final Grade (overrides your calculated average)</label>
        <input
          id="edit-course-final-grade"
          type="number"
          min={0}
          max={100}
          value={form.final_grade}
          onChange={(event) => updateField("final_grade", Number(event.target.value))}
          className="--input mt-1 w-full rounded-lg border border-slate-700 bg-transparent text-white"
        />
      </div>

      <div>
        <input
          id="edit-course-professor"
          value={form.professor}
          onChange={(event) => updateField("professor", event.target.value)}
          className="--input mt-1 w-full rounded-lg border border-slate-700 bg-transparent text-white"
          placeholder="Professor"
          required
        />
      </div>

      <div className="flex items-center gap-3">
        <label htmlFor="edit-required-checkbox" className="text-sm text-slate-200">
          Required?
        </label>
        <input
          id="edit-required-checkbox"
          type="checkbox"
          checked={form.required}
          onChange={(event) => updateField("required", event.target.checked)}
          className="--input h-4 w-4 rounded border-slate-700 !bg-slate-900 !text-gold"
        />
      </div>

      <div className="flex gap-3">
        <div>
          <label htmlFor="edit-course-start-date" className="block text-sm text-slate-200">Starts</label>
          <input
            id="edit-course-start-date"
            type="date"
            value={form.start_date ?? ""}
            onChange={(event) => updateField("start_date", event.target.value || null)}
            className="--input mt-1 rounded-lg border border-slate-700 bg-transparent text-white"
          />
        </div>
        <div>
          <label htmlFor="edit-course-end-date" className="block text-sm text-slate-200">Ends</label>
          <input
            id="edit-course-end-date"
            type="date"
            value={form.end_date ?? ""}
            onChange={(event) => updateField("end_date", event.target.value || null)}
            className="--input mt-1 rounded-lg border border-slate-700 bg-transparent text-white"
          />
        </div>
      </div>

      <div className="edit_category_grid">
        {Object.values(GradeCategory).map((category) => (
            <div key={category} className="editCategoryWeightItem">
            <label htmlFor={`category-weight-${category}`} className="editCategoryWeightLabel">
                {category}
            </label>
            <input
                id={`category-weight-${category}`}
                type="number"
                className="editCategoryWeightInput"
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
          onClick={() => onSubmit()}
          className="rounded-lg !bg-gold !text-slate-950"
          disabled={submitting}
        >
          {submitting ? "Saving..." : "Save Changes"}
        </button>
      </div>
    </div>
  );
}