import {GradeCategory, Grade} from "../types"
import { isOverMax, marksOver } from "../bonus"
import { atZero, isSplit } from "../subcategory"
import { trimNumber } from "../../../shared/utils/numberUtils"
import HelpTip from "../../../shared/components/HelpTip"


/** A category's heading, its weight and grades, and the edit, add, delete and split handlers. */
interface GradeCategoryColumnProps {
  readonly title: string;
  readonly category: GradeCategory;
  /** The category's weight in the course; 0 has nothing to split. */
  readonly categoryWeight: number;
  readonly items: Grade[];
  readonly onEditItem: (itemId: string) => void;
  readonly onAddGrade: (category: GradeCategory) => void;
  readonly onDeleteItem: (item: Grade) => void;
  readonly onSplit: (category: GradeCategory) => void;
}

/**
 * One category's grades as rows, marking bonus and dropped ones, with add and delete buttons,
 * and how its weight is shared: evenly, or split by subcategory weights (D29).
 */
export default function GradeCategoryColumn({
  title, category, categoryWeight, items, onEditItem, onAddGrade, onDeleteItem, onSplit,
}: GradeCategoryColumnProps) {
  const split = isSplit(items);
  const weight = trimNumber(categoryWeight);
  const uncounted = atZero(items).filter((item) => !item.excluded);
  return (
    <div className="categoryColumn">
      <div className="categoryTitle">
        {/* h2, not h3. The page heading is the course title, and skipping a
            level leaves anyone navigating by headings unable to tell whether
            they have missed a section. */}
        <h2>{title}</h2>
        <button
          type="button"
          className="addGradeButton"
          onClick={() => onAddGrade(category)}
          aria-label={`Add grade to ${title}`}
        >
          +
        </button>
      </div>
      {categoryWeight > 0 && items.length > 0 && (
        <div className="splitLine">
          <span>{split ? `Split by subcategory weights` : `${weight}% shared evenly`}</span>
          <button
            type="button"
            className="splitButton"
            onClick={() => onSplit(category)}
            aria-label={split ? `Change how ${category}'s ${weight}% is split` : `Split ${category}'s ${weight}%`}
          >
            {split ? "Change split" : "Split weight"}
          </button>
          <HelpTip label="What subcategory weights are">
            Subcategory weights split {category}&apos;s {weight}% between its items, so each mark counts by
            its own share and you can enter it exactly as your professor gave it, out of whatever it was
            marked out of. They must add up to {weight}%. With none set, the {weight}% is shared evenly:
            every item counts the same, whatever it&apos;s out of. A new item joins a split at 0% until you
            change it. Deleting or moving one shares its weight among the rest in proportion, and changing
            {" "}{category}&apos;s weight scales the split to match. A dropped item keeps its share, and the
            rest count for it.
          </HelpTip>
        </div>
      )}
      <ul className="categoryList">
        {items.map((item) => {
          // Scoring above the maximum is allowed and always has been, but it
          // rendered as a plain "11/10" -- indistinguishable from a typo.
          const over = isOverMax(item);
          // A dropped mark stays visible -- you want to see what was dropped --
          // but must not look like it is counting.
          const dropped = item.excluded;
          const classes = ["gradeRow"];
          if (over && !dropped) classes.push("gradeRowBonus");
          if (dropped) classes.push("gradeRowDropped");
          return (
          <li key={item.id} className="gradeRowItem">
            <button
              type="button"
              className={classes.join(" ")}
              onClick={() => onEditItem(item.id)}
              title={
                dropped
                  ? "Not counted toward the course"
                  : over ? `${marksOver(item)} over the maximum` : undefined
              }
            >
              <span>{item.name}</span>
              <span>
                {over && !dropped && <span className="bonusMark" aria-hidden="true">★ </span>}
                {item.score ?? "-"}/{item.max_score}
                {over && !dropped && <span className="srOnly"> (bonus)</span>}
                {split && (
                  <span className={item.subcategory_weight ? "shareTag" : "shareTag shareTagZero"}>
                    {trimNumber(item.subcategory_weight ?? 0)}%
                  </span>
                )}
                {dropped && <span className="droppedTag">dropped</span>}
              </span>
            </button>
            <button
              type="button"
              className="deleteGradeButton"
              onClick={(e) => {
                e.stopPropagation();
                onDeleteItem(item);
              }}
              aria-label={`Delete ${item.name}`}
            >
              ×
            </button>
          </li>
          );
        })}
      </ul>
      {uncounted.length > 0 && (
        <p className="splitWarning" role="note">
          {uncounted.map((item) => item.name).join(", ")} {uncounted.length === 1 ? "is" : "are"} at 0%, so{" "}
          {uncounted.length === 1 ? "it doesn't" : "they don't"} count yet. Change the split to give{" "}
          {uncounted.length === 1 ? "it" : "them"} a share.
        </p>
      )}
    </div>
  );
}
