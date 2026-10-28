import { useState } from "react";
import ProgressBar from "./ProgressBar";
import { CategorySpend } from "../types";
import { formatMoney } from "../money";

/** Props for the spending-by-category section. */
interface WhereItWentProps {
  readonly entries: readonly CategorySpend[];
  /** Opens the income split; absent on the account page, which shows no page actions. */
  readonly onEditSplit?: () => void;
  /** Opens the categories dialog; absent on the account page. */
  readonly onEditCategories?: () => void;
  /** Set this account's limit for a category, or clear it with null; account page only. */
  readonly onSetLimit?: (
    categoryId: string,
    limit: number | null,
    /** False sets the standing limit; true sets only the month on screen. */
    thisMonthOnly: boolean,
  ) => Promise<void>;
  /** True while a newly picked month's figures are still loading. */
  readonly pending?: boolean;
}

/** What a row says under its bar, left or over; null without a limit. */
function limitNote(entry: CategorySpend): string | null {
  if (entry.limit === null) return null;
  if (entry.remaining < 0) return `${formatMoney(-entry.remaining)} over`;
  return `${formatMoney(entry.remaining)} left`;
}

/**
 * Spending by category for the month; on an account's page each limit is editable.
 * An empty limit box clears the limit rather than setting zero.
 */
export default function WhereItWent({
  entries,
  onEditSplit,
  onEditCategories,
  onSetLimit,
  pending = false,
}: WhereItWentProps) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [justThisMonth, setJustThisMonth] = useState(false);
  const [saving, setSaving] = useState(false);

  async function commit(categoryId: string) {
    if (!onSetLimit) return;
    setSaving(true);
    try {
      // An empty box clears whichever limit is being edited rather than setting
      // one of nothing. The two are different instructions, and a blank field is
      // far likelier to mean "never mind" than "allow zero".
      await onSetLimit(
        categoryId,
        draft.trim() === "" ? null : Number(draft),
        justThisMonth,
      );
      setEditing(null);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="categorySpend" aria-busy={pending}>
      <div className="sectionHeading">
        <h2>Where it went</h2>
      </div>

      {entries.length > 0 ? (
        <ul className="categoryList">
          {entries.map((entry) => {
            const id = entry.category_id;
            // Uncategorised has no row to hang a limit on, so it is never
            // editable however the page is wired.
            const editable = onSetLimit !== undefined && id !== null;
            // `id !== null` is load-bearing. `editing` starts as null and
            // Uncategorised's id *is* null, so `editing === id` alone was true
            // on first render and opened that row as a live editor, unprompted.
            const isEditing = id !== null && editing === id;
            const note = limitNote(entry);

            return (
              <li key={id ?? "none"}>
                {/* The li stacks and this line spreads. Putting
                    `justify-content` on the li works only while a row is
                    exactly two spans, which stops being true the moment a bar
                    appears below -- budget.css says so beside the rule. */}
                <div className="categoryTop">
                  <span className="categoryName">{entry.category_name}</span>

                  {isEditing ? (
                    <span className="plannedEdit">
                      <input
                        className="loginInput plannedInput"
                        type="number"
                        min={0}
                        step="0.01"
                        value={draft}
                        autoFocus
                        onChange={(event) => setDraft(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") commit(id!);
                          if (event.key === "Escape") setEditing(null);
                        }}
                        aria-label={`Limit for ${entry.category_name} on this account`}
                      />
                      {/* Which of the two is being set. Unchecked edits the
                          standing limit, which is what carries into every
                          month; checked touches only the month on screen and
                          leaves the standing figure alone. */}
                      <label className="limitScope small-text muted">
                        <input
                          type="checkbox"
                          checked={justThisMonth}
                          onChange={(event) => setJustThisMonth(event.target.checked)}
                        />
                        This month only
                      </label>
                      <button
                        type="button"
                        className="buttons"
                        onClick={() => commit(id!)}
                        disabled={saving}
                      >
                        Save
                      </button>
                    </span>
                  ) : (
                    <FigureCell
                      entry={entry}
                      editable={editable}
                      onEdit={() => {
                        setEditing(id);
                        setDraft(entry.limit === null ? "" : String(entry.limit));
                        // Opens on whichever this row is already showing, so
                        // editing an overridden month edits that month by
                        // default rather than silently rewriting the standing
                        // figure behind it.
                        setJustThisMonth(entry.limit_is_override);
                      }}
                    />
                  )}
                </div>

                {/* Only where there is something to measure against. A bar with
                    no target is a shape that means nothing. */}
                {entry.limit !== null && (
                  <>
                    <ProgressBar
                      value={entry.actual}
                      max={entry.limit}
                      percent={entry.used_percent}
                      label={`${entry.category_name} spend against limit`}
                    />
                    <span className="small-text muted plannedNote">
                      {note}
                      {entry.limit_is_override && " · this month only"}
                    </span>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="small-text muted">Nothing spent this month yet.</p>
      )}

      {/* The two things you come here to change. This section used to render
          only when there was spending to show, which hid both controls in
          exactly the month you are most likely to be setting categories up. */}
      {(onEditSplit || onEditCategories) && (
        <div className="categoryActions">
          {onEditSplit && (
            <button type="button" className="buttons addCourseButton" onClick={onEditSplit}>
              Income split
            </button>
          )}
          {onEditCategories && (
            <button type="button" className="buttons addCourseButton" onClick={onEditCategories}>
              Categories
            </button>
          )}
        </div>
      )}
    </section>
  );
}

/** A row's amount and its limit; a labelled button when editable, plain text otherwise. */
function FigureCell({
  entry,
  editable,
  onEdit,
}: {
  readonly entry: CategorySpend;
  readonly editable: boolean;
  readonly onEdit: () => void;
}) {
  const text =
    entry.limit === null
      ? formatMoney(entry.actual)
      : `${formatMoney(entry.actual)} / ${formatMoney(entry.limit)}`;

  if (!editable) return <span className="categoryAmount">{text}</span>;

  // Labelled, because the button's own text is a pair of amounts. Read aloud,
  // "$412.00 / $400.00, button" says nothing about what pressing it does.
  const action =
    entry.limit === null
      ? `Set a limit for ${entry.category_name} on this account`
      : `Change the limit for ${entry.category_name} on this account`;

  return (
    <button
      type="button"
      className="plannedFigure categoryAmount"
      onClick={onEdit}
      aria-label={action}
      title={action}
    >
      {text}
    </button>
  );
}
