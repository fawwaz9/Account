import {GradeCategory, Grade} from "../types"


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
        {items.map((item) => (
          <li key={item.id} className="gradeRowItem">
            <button
              type="button"
              className="gradeRow"
              onClick={() => onEditItem(item.id)}
            >
              <span>{item.name}</span>
              <span>
                {item.score ?? "-"}/{item.max_score}
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
        ))}
      </ul>
    </div>
  );
}