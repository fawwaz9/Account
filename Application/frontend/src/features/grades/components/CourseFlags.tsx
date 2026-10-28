/** The three course flags a form holds. */
interface CourseFlagState {
  no_final: boolean;
  transfer_credit: boolean;
  archived: boolean;
}

/** The form's flag values, its field setter, and an id prefix. */
interface CourseFlagsProps {
  readonly form: CourseFlagState;
  readonly updateField: <K extends keyof CourseFlagState>(key: K, value: boolean) => void;
  /** Distinguishes the ids from the other form's when both are on the page. */
  readonly idPrefix: string;
}

/** One flag's key, its label, and a hint saying what it changes. */
interface FlagDefinition {
  readonly key: keyof CourseFlagState;
  readonly label: string;
  /** Says what the flag *does*, since none of them are self-explanatory. */
  readonly hint: string;
}

/** The three flags in display order. */
const FLAGS: FlagDefinition[] = [
  {
    key: "no_final",
    label: "No final exam",
    hint: "Stops this course asking for a final grade in Attention.",
  },
  {
    key: "transfer_credit",
    label: "Transfer credit",
    hint: "Counts toward credits completed; no score, and stays out of every average.",
  },
  {
    key: "archived",
    label: "Archived",
    hint: "Still searchable and still in the average, but out of credits completed.",
  },
];

/** The course-flag checkboxes shared by the add and edit forms, each with its own hint. */
export default function CourseFlags({ form, updateField, idPrefix }: CourseFlagsProps) {
  return (
    <fieldset className="courseFlags">
      <legend className="block text-sm text-slate-200">How this course counts</legend>

      {FLAGS.map((flag) => (
        <div key={flag.key} className="courseFlag">
          <input
            id={`${idPrefix}-${flag.key}`}
            type="checkbox"
            checked={form[flag.key]}
            onChange={(event) => updateField(flag.key, event.target.checked)}
            className="--input h-4 w-4 rounded border-slate-700 !bg-slate-900 !text-gold"
          />
          <label htmlFor={`${idPrefix}-${flag.key}`} className="courseFlagLabel">
            <span className="courseFlagName">{flag.label}</span>
            <span className="courseFlagHint">{flag.hint}</span>
          </label>
        </div>
      ))}
    </fieldset>
  );
}
