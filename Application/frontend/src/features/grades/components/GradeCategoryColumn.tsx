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
        <h3>{title}</h3>
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
          return (
          <li key={item.id} className="gradeRowItem">
            <button
              type="button"
              className={over ? "gradeRow gradeRowBonus" : "gradeRow"}
              onClick={() => onEditItem(item.id)}
              title={over ? `${marksOver(item)} over the maximum` : undefined}
            >
              <span>{item.name}</span>
              <span>
                {over && <span className="bonusMark" aria-hidden="true">★ </span>}
                {item.score ?? "-"}/{item.max_score}
                {over && <span className="srOnly"> (bonus)</span>}
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