import { GradeCategory } from "../types";
import { isAdditive, scoringWeight } from "../bonus";

/** Category weights in percent; a missing key is unset. */
type Weights = Partial<Record<GradeCategory, number>>;

/** The weights, their change handler, an id prefix, and the class names each form uses. */
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
 * A weight input per category, bonus held apart below a total of the scoring weights.
 * Shared by the add and edit course forms, so both treat bonus the same way.
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
