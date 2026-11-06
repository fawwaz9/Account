import { useEffect, useState } from "react";
import Modal from "../../../shared/components/Modal";
import { useAuth } from "../../../app/auth/AuthContext";
import { trimNumber } from "../../../shared/utils/numberUtils";
import { setSubcategoryWeights } from "../api";
import { Grade, GradeCategory } from "../types";
import { addsUp, evenSplit, isSplit, toCents } from "../subcategory";
import { getErrorMessage } from "./AddCourseModal";

/** The category to split, its weight and items, and close and saved callbacks. */
interface SubcategoryWeightsModalProps {
  readonly open: boolean;
  readonly courseId: string;
  readonly category: GradeCategory;
  readonly categoryWeight: number;
  readonly items: readonly Grade[];
  readonly onClose: () => void;
  readonly onSaved: () => void;
}

/** The boxes' starting values: the stored split, or the even share it would replace. */
function startingValues(items: readonly Grade[], weight: number): Record<string, string> {
  const even = evenSplit(weight, items.length);
  return Object.fromEntries(
    items.map((item, index) => [
      item.id,
      String(isSplit(items) ? item.subcategory_weight ?? 0 : even[index]),
    ])
  );
}

/**
 * Split a category's weight between its items (D29). Save stays off until the shares add up
 * to the category's weight: that is a hard limit, and the server refuses anything else too.
 */
export default function SubcategoryWeightsModal({
  open,
  courseId,
  category,
  categoryWeight,
  items,
  onClose,
  onSaved,
}: SubcategoryWeightsModalProps) {
  const { user } = useAuth();
  const [values, setValues] = useState<Record<string, string>>(() => startingValues(items, categoryWeight));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setValues(startingValues(items, categoryWeight));
    setError(null);
  }, [items, categoryWeight, open]);

  if (!open) return null;

  const shares = items.map((item) => Number(values[item.id] || 0));
  const valid = shares.every((share) => Number.isFinite(share) && share >= 0);
  const total = toCents(shares.reduce((sum, share) => sum + (Number.isFinite(share) ? share : 0), 0));
  const fits = valid && addsUp(shares, categoryWeight);
  const gap = toCents(categoryWeight - total);
  const weight = trimNumber(categoryWeight);

  async function save(weights: Record<string, number> | null) {
    if (!user) return;
    setSaving(true);
    setError(null);
    try {
      await setSubcategoryWeights(user.id, courseId, category, weights);
      onSaved();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!fits) return;
    void save(Object.fromEntries(items.map((item, index) => [item.id, shares[index]])));
  }

  return (
    <Modal title={`Split ${category}'s ${weight}%`} onClose={onClose}>
      <form className="calForm shareForm" onSubmit={handleSubmit}>
        <p className="taskEditNote">
          Give each item its share of {category}&apos;s {weight}%, as the syllabus does. They must add up
          to {weight}%. Each mark then counts by its share, whatever it&apos;s out of.
        </p>

        {items.map((item) => (
          <div className="shareRow" key={item.id}>
            <label htmlFor={`share-${item.id}`} className="shareRowName">
              {item.name}
              {item.excluded && <span className="droppedTag">dropped</span>}
            </label>
            <span className="shareRowOutOf">out of {trimNumber(item.max_score)}</span>
            <span className="shareRowInput">
              <input
                id={`share-${item.id}`}
                className="calInput"
                type="number"
                inputMode="decimal"
                min={0}
                max={categoryWeight}
                step={0.01}
                value={values[item.id] ?? ""}
                onChange={(event) => setValues((current) => ({ ...current, [item.id]: event.target.value }))}
              />
              <span aria-hidden="true">%</span>
            </span>
          </div>
        ))}

        <p className={fits ? "shareTotal" : "shareTotal shareTotalOff"} role="status">
          {!valid && "A share can't be negative."}
          {valid && fits && `Adds up to ${weight}%.`}
          {valid && !fits && gap > 0 && `Adds up to ${trimNumber(total)}%: ${trimNumber(gap)}% left to share.`}
          {valid && !fits && gap < 0 && `Adds up to ${trimNumber(total)}%: ${trimNumber(-gap)}% too much.`}
        </p>

        {error && <p className="calError">{error}</p>}

        <div className="calFormActions">
          {isSplit(items) && (
            <button type="button" className="calButton" onClick={() => void save(null)} disabled={saving}>
              Share evenly again
            </button>
          )}
          <button type="button" className="calButton" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className="calButton calButtonPrimary" disabled={saving || !fits}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
