import { useState } from "react";
import { EstimateRatio } from "../types";

/** The estimate ratio, and the handler that turns its use on or off. */
interface EstimateRatioCardProps {
  readonly ratio: EstimateRatio | null;
  /** Turn the forecast's use of the ratio on or off. */
  readonly onApply: (on: boolean) => Promise<void>;
}

/**
 * How long tasks really take against their estimates, with the switch for the forecast to use it.
 * Until enough tasks qualify it says how many; the estimates themselves are never rewritten.
 */
export default function EstimateRatioCard({ ratio, onApply }: EstimateRatioCardProps) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!ratio || ratio.tasks === 0) return null;

  async function toggle(on: boolean) {
    setSaving(true);
    setError(null);
    try {
      await onApply(on);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't change that.");
    } finally {
      setSaving(false);
    }
  }

  if (ratio.ratio === null) {
    return (
      <section className="estimateRatio">
        <h2 className="taskGroupTitle">Your estimates</h2>
        <p className="small-text">
          {ratio.tasks} of {ratio.needed} finished tasks have both an estimate and the time it took.
          How your estimates run shows up at {ratio.needed}.
        </p>
      </section>
    );
  }

  const r = ratio.ratio;
  const reading =
    r === 1 ? "take about what you estimate"
      : r > 1 ? `take ${r.toFixed(2)}× your estimates`
        : `take ${r.toFixed(2)}× your estimates, less than you think`;

  return (
    <section className="estimateRatio">
      <h2 className="taskGroupTitle">Your estimates</h2>
      <p className="small-text">
        Tasks {reading}, across {ratio.tasks} finished in the last 90 days.
      </p>
      <label className="estimateRatioApply">
        <input type="checkbox" checked={ratio.applied} disabled={saving}
               onChange={(event) => void toggle(event.target.checked)} />
        Use it in the workload forecast
      </label>
      {error && <p className="small-text error" role="alert">{error}</p>}
    </section>
  );
}
