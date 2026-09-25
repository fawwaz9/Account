import { useState } from "react";
import ProgressBar from "./ProgressBar";
import { CategorySpend } from "../types";
import { formatMoney } from "../money";

interface WhereItWentProps {
  readonly entries: readonly CategorySpend[];
  /**
   * Optional, and absent on purpose for one caller. The account detail page
   * reuses this section to break down a single account, where page-level
   * budget controls would be out of place -- so with no handlers, no actions.
   */
  readonly onEditSplit?: () => void;
  readonly onEditCategories?: () => void;
  /**
   * Set this month's limit for one category, or clear it back to the standing
   * one with `null`. Absent on the account detail page, where the rows carry no
   * limit to edit.
   */
  readonly onSetLimit?: (categoryId: string, limit: number | null) => Promise<void>;
  /** True while a newly-picked month's figures are still in flight. */
  readonly pending?: boolean;
}

/** What the row says under the bar, or null when there is nothing to say. */
function limitNote(entry: CategorySpend): string | null {
  if (entry.limit === null) return null;
  if (entry.remaining < 0) return `${formatMoney(-entry.remaining)} over`;
  return `${formatMoney(entry.remaining)} left`;
}

export default function WhereItWent({
  entries,
  onEditSplit,
  onEditCategories,
  onSetLimit,
  pending = false,
}: WhereItWentProps) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);

  async function commit(categoryId: string) {
    if (!onSetLimit) return;
    setSaving(true);
    try {
      // An empty box clears this month's override rather than setting a limit
      // of nothing. The two are different instructions and the blank one is far
      // likelier to mean "never mind" than "allow zero".
      const next = draft.trim() === "" ? null : Number(draft);
      await onSetLimit(categoryId, next);
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
            // editable however the parent is wired.
            const editable = onSetLimit !== undefined && id !== null;
            // `id !== null` is load-bearing and not a tidy-up. `editing` starts
            // as null and Uncategorised's id *is* null, so `editing === id`
            // was true on first render and that row opened as a live editor
            // before anybody clicked anything -- on the one category that can
            // never have a limit.
            const isEditing = id !== null && editing === id;
            const note = limitNote(entry);

            // Every row stacks the same way, with or without a bar, so the
            // line that spreads is `.categoryTop` rather than the `li` itself.
            // A conditional class used to mark the rows with a bar; it turned
            // out to be what kept the plain rows from spreading at all.
            return (
              <li key={id ?? "none"}>
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
                        aria-label={`Limit for ${entry.category_name} this month`}
                      />
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

/**
 * The amount, and the limit it is judged against when there is one.
 *
 * A plain span when nothing is editable, so the account detail page and
 * Uncategorised rows render exactly as they did before limits existed rather
 * than growing a button that does nothing.
 */
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
  // "$412.00 / $400.00, button" says nothing about what pressing it does -- and
  // this is the only way to set a limit for a single month.
  const action =
    entry.limit === null
      ? `Set a limit for ${entry.category_name} this month`
      : `Change this month's limit for ${entry.category_name}`;

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
