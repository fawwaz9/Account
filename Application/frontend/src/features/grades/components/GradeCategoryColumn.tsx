import {GradeCategory, Grade} from "../types"
import { isOverMax, marksOver } from "../bonus"
import { atZero, isSplit } from "../subcategory"
import { trimNumber } from "../../../shared/utils/numberUtils"
import HelpTip from "../../../shared/components/HelpTip"


/** A category's heading, its weight and grades, and the edit, add, delete and split handlers. */
interface GradeCategoryColumnProps {
  readonly title: string;
  readonly category: GradeCategory;
  /** The category's weight in the course; 0 has nothing to share. */
  readonly categoryWeight: number;
  /** Whether the category is marked by points when it isn't split. */
  readonly byPoints: boolean;
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
  title, category, categoryWeight, byPoints, items, onEditItem, onAddGrade, onDeleteItem, onSplit,
}: GradeCategoryColumnProps) {
  const split = isSplit(items);
  let sharing = `${trimNumber(categoryWeight)}% shared evenly`;
  if (split) sharing = "Split by subcategory weights";
  else if (byPoints) sharing = `${trimNumber(categoryWeight)}% shared by points`;
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
          <span>{sharing}</span>
          <button
            type="button"
            className="splitButton"
            onClick={() => onSplit(category)}
            aria-label={`Change how ${category}'s ${weight}% is shared`}
          >
            Change
          </button>
          <HelpTip label="How a category's weight is shared">
            {category}&apos;s {weight}% is shared between its items one of three ways. Evenly, the default:
            every item counts the same, whatever it&apos;s out of. By points, for a professor who adds up
            marks: total earned over total possible, so an item out of 100 counts ten times one out of 10.
            Or by subcategory weights, your own share for each item, so you can enter each mark exactly as
            your professor gave it. Subcategory weights must add up to {weight}%. A new item joins them at
            0% until you change it. Deleting or moving one shares its weight among the rest in proportion,
            and changing {category}&apos;s weight scales them to match. A dropped item keeps its share, and
            the rest count for it.
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
