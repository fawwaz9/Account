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
}

export default function WhereItWent({
  entries,
  onEditSplit,
  onEditCategories,
}: WhereItWentProps) {
  return (
    <section className="categorySpend">
      <div className="sectionHeading">
        <h2>Where it went</h2>
      </div>

      {entries.length > 0 ? (
        <ul className="categoryList">
          {entries.map((entry) => (
            <li key={entry.category_id ?? "none"}>
              <span>{entry.category_name}</span>
              <span className="categoryAmount">{formatMoney(entry.actual)}</span>
            </li>
          ))}
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
