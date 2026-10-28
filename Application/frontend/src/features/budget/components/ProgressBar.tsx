/** Props for a spend bar. */
interface ProgressBarProps {
  readonly value: number;
  readonly max: number;
  /** Server's `used_percent`; passed, not derived, so it matches the server's rounding. */
  readonly percent?: number;
  readonly label?: string;
}

/** Spend against a target; overspending shows by colour, never by a bar past its track. */
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
