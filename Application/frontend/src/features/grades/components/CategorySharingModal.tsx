import { useEffect, useState } from "react";
import Modal from "../../../shared/components/Modal";
import { useAuth } from "../../../app/auth/AuthContext";
import { trimNumber } from "../../../shared/utils/numberUtils";
import { setCategorySharing } from "../api";
import { Grade, GradeCategory } from "../types";
import { addsUp, evenSplit, isSplit, toCents } from "../subcategory";
import { getErrorMessage } from "./AddCourseModal";

/** How a category shares its weight between its items (D29). */
export type Sharing = "even" | "points" | "split";

/** The category, its weight, items and current sharing, and close and saved callbacks. */
interface CategorySharingModalProps {
  readonly open: boolean;
  readonly courseId: string;
  readonly category: GradeCategory;
  readonly categoryWeight: number;
  readonly items: readonly Grade[];
  /** Whether the category is marked by points when it isn't split. */
  readonly byPoints: boolean;
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

/** The category's sharing now: a split wins, then by points, then even. */
export function sharingOf(items: readonly Grade[], byPoints: boolean): Sharing {
  if (isSplit(items)) return "split";
  return byPoints ? "points" : "even";
}

/**
 * Choose how a category's weight is shared: evenly, by points, or split by subcategory
 * weights. A split can't be saved until it adds up to the category's weight: that is a hard
 * limit, and the server refuses anything else too.
 */
export default function CategorySharingModal({
  open,
  courseId,
  category,
  categoryWeight,
  items,
  byPoints,
  onClose,
  onSaved,
}: CategorySharingModalProps) {
  const { user } = useAuth();
  const [choice, setChoice] = useState<Sharing>(() => sharingOf(items, byPoints));
  const [values, setValues] = useState<Record<string, string>>(() => startingValues(items, categoryWeight));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setChoice(sharingOf(items, byPoints));
    setValues(startingValues(items, categoryWeight));
    setError(null);
  }, [items, categoryWeight, byPoints, open]);

  if (!open) return null;

  const shares = items.map((item) => Number(values[item.id] || 0));
  const valid = shares.every((share) => Number.isFinite(share) && share >= 0);
  const total = toCents(shares.reduce((sum, share) => sum + (Number.isFinite(share) ? share : 0), 0));
  const fits = valid && addsUp(shares, categoryWeight);
  const gap = toCents(categoryWeight - total);
  const weight = trimNumber(categoryWeight);
  const canSave = choice !== "split" || fits;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user || !canSave) return;
    setSaving(true);
    setError(null);
    try {
      await setCategorySharing(user.id, courseId, category, {
        weights: choice === "split" ? Object.fromEntries(items.map((item, index) => [item.id, shares[index]])) : null,
        by_points: choice === "points",
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  const options: { value: Sharing; label: string; note: string }[] = [
    { value: "even", label: "Evenly", note: "Every item counts the same, whatever it's out of." },
    {
      value: "points",
      label: "By points",
      note: "Total marks earned over total possible, so an item out of 100 counts ten times one out of 10.",
    },
    { value: "split", label: "My own weights", note: `Give each item its share of the ${weight}%, as the syllabus does.` },
  ];

  return (
    <Modal title={`How ${category}'s ${weight}% is shared`} onClose={onClose}>
      <form className="calForm shareForm" onSubmit={handleSubmit}>
        <fieldset className="shareChoices">
          <legend className="srOnly">How {category}&apos;s {weight}% is shared</legend>
          {options.map((option) => (
            <label key={option.value} className="shareChoice">
              <input
                type="radio"
                name="sharing"
                value={option.value}
                checked={choice === option.value}
                onChange={() => setChoice(option.value)}
              />
              <span>
                <strong>{option.label}</strong>
                <span className="shareChoiceNote">{option.note}</span>
              </span>
            </label>
          ))}
        </fieldset>

        {choice === "split" && (
          <>
            <p className="taskEditNote">
              They must add up to {weight}%. Each mark then counts by its share, whatever it&apos;s out of.
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
          </>
        )}

        {error && <p className="calError">{error}</p>}

        <div className="calFormActions">
          <button type="button" className="calButton" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className="calButton calButtonPrimary" disabled={saving || !canSave}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
