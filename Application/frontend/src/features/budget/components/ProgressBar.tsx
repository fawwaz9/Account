interface ProgressBarProps {
  readonly value: number;
  readonly max: number;
  /**
   * The server's `used_percent`. Passed rather than derived, because the server
   * already computes this figure and rounds it to 1dp: recomputing `value / max`
   * here is a second opinion, and the two disagree at the `close` boundary --
   * 89.96 rounds to 90.0 there and stays 0.8996 here, so one says "close" and
   * the other does not for the same money.
   */
  readonly percent?: number;
  readonly label?: string;
}

/**
 * Spend against a target. Overspending is shown by colour rather than by a bar
 * running past its track, which would just look broken.
 */
export default function ProgressBar({ value, max, percent, label }: ProgressBarProps) {
  const hasTarget = max > 0;
  // Falls back to deriving it only when the caller has no server figure to give.
  const used = percent ?? (hasTarget ? (value / max) * 100 : 0);
  const width = Math.min(used, 100);

  let state = "under";
  if (!hasTarget) state = "none";
  else if (used > 100) state = "over";
  else if (used >= 90) state = "close";

  const rounded = Math.round(max) || 100;

  return (
    <div
      className="progressTrack"
      role="progressbar"
      // Clamped: a progressbar whose valuenow exceeds its valuemax is invalid
      // ARIA, and overspending is exactly when that happened. The real figure
      // is still announced, through valuetext.
      aria-valuenow={Math.min(Math.round(value), rounded)}
      aria-valuemin={0}
      aria-valuemax={rounded}
      aria-valuetext={hasTarget ? `${used.toFixed(1)}% of target used` : "No target set"}
      aria-label={label ?? "Spend against target"}
    >
      <div className={`progressFill progressFill--${state}`} style={{ width: `${width}%` }} />
    </div>
  );
}
