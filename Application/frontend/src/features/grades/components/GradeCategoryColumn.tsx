import {GradeCategory, Grade} from "../types"
import { isOverMax, marksOver } from "../bonus"


interface GradeCategoryColumnProps {
  readonly title: string;
  readonly category: GradeCategory;
  readonly items: Grade[];
  readonly onEditItem: (itemId: string) => void;
  readonly onAddGrade: (category: GradeCategory) => void;
  readonly onDeleteItem: (item: Grade) => void;
}

export default function GradeCategoryColumn({ title, category, items, onEditItem, onAddGrade, onDeleteItem }: GradeCategoryColumnProps) {
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
    </div>
  );
}