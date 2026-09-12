import { GradeCategory } from "../types";
import { isAdditive, scoringWeight } from "../bonus";

type Weights = Partial<Record<GradeCategory, number>>;

interface CategoryWeightsProps {
  readonly weights: Weights;
  readonly onChange: (next: Weights) => void;
  readonly idPrefix: string;
  readonly gridClass: string;
  readonly itemClass: string;
  readonly labelClass: string;
  readonly inputClass: string;
}

/**
 * The category weight inputs, with the additive ones held apart.
 *
 * Bonus arrives through Object.values(GradeCategory) like every other category,
 * which would drop it into the same grid as a ninth identical box -- implying it
 * is one of the parts the course is divided into, when the whole point is that
 * it sits outside them. Separating it is the only honest way to draw a grid
 * whose boxes are meant to total 100.
 *
 * Shared by the add and edit forms, which were structurally identical here and
 * differed only in class names. One copy, so the two cannot disagree about what
 * bonus means.
 */
export default function CategoryWeights({
  weights,
  onChange,
  idPrefix,
  gridClass,
  itemClass,
  labelClass,
  inputClass,
}: CategoryWeightsProps) {
  const categories = Object.values(GradeCategory);
  const scoring = categories.filter((category) => !isAdditive(category));
  const additive = categories.filter(isAdditive);
  const total = scoringWeight(weights);

  function box(category: GradeCategory) {
    return (
      <div key={category} className={itemClass}>
        <label htmlFor={`${idPrefix}-category-weight-${category}`} className={labelClass}>
          {category}
        </label>
        <input
          id={`${idPrefix}-category-weight-${category}`}
          type="number"
          step="any"
          className={inputClass}
          placeholder="0"
          min={0}
          max={100}
          value={weights?.[category] ?? ""}
          onChange={(e) => {
            const raw = e.target.value;
            onChange({ ...weights, [category]: raw === "" ? undefined : Number(raw) });
          }}
        />
      </div>
    );
  }

  return (
    <>
      <div className={gridClass}>{scoring.map(box)}</div>

      {/* Only the scoring categories are totalled, so a course carrying bonus
          still reads as being marked out of 100 rather than 105. */}
      <p className={total === 100 ? "weightTotal weightTotalExact" : "weightTotal"}>
        marked out of <strong>{Math.round(total * 100) / 100}</strong>
        {total !== 100 && total > 0 && " — these normally total 100"}
      </p>

      <div className="bonusWeights">
        <p className="bonusWeightsNote">
          Added on top of the {Math.round(total * 100) / 100 || 100} above, not counted within it.
        </p>
        <div className={gridClass}>{additive.map(box)}</div>
      </div>
    </>
  );
}
