interface ProgressBarProps {
  readonly value: number;
  readonly max: number;
  readonly label?: string;
}

/**
 * Spend against a target. Overspending is shown by colour rather than by a bar
 * running past its track, which would just look broken.
 */
export default function ProgressBar({ value, max, label }: ProgressBarProps) {
  const hasTarget = max > 0;
  const ratio = hasTarget ? value / max : 0;
  const width = Math.min(ratio, 1) * 100;

  let state = "under";
  if (!hasTarget) state = "none";
  else if (ratio > 1) state = "over";
  else if (ratio >= 0.9) state = "close";

  return (
    <div
      className="progressTrack"
      role="progressbar"
      aria-valuenow={Math.round(value)}
      aria-valuemin={0}
      aria-valuemax={Math.round(max) || 100}
      aria-label={label ?? "Spend against target"}
    >
      <div className={`progressFill progressFill--${state}`} style={{ width: `${width}%` }} />
    </div>
  );
}
