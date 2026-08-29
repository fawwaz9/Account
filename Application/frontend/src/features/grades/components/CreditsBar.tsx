interface CreditsBarProps {
  readonly completed: number;
  readonly inProgress: number;
  readonly target: number;
}

export default function CreditsBar({ completed, inProgress, target }: CreditsBarProps) {
  const safeTarget = target > 0 ? target : 1;
  const completedPct = Math.min((completed / safeTarget) * 100, 100);
  const inProgressPct = Math.min((inProgress / safeTarget) * 100, 100 - completedPct);
  const remaining = Math.max(target - completed, 0);

  // Quarter marks, so the bar reads against the degree rather than a raw width.
  const ticks = [0.5, 0.8].map((fraction) => Math.round(target * fraction));

  return (
    <div className="creditsPanel">
      <div className="creditsHeader">
        <span className="creditsTitle">Credits</span>
        <span className="creditsLegend">
          <span className="legendSwatch legendDone" /> completed
          <span className="legendSwatch legendProgress" /> in progress
        </span>
      </div>

      <div className="creditsRow">
        <div
          className="creditsTrack"
          role="progressbar"
          aria-valuenow={Math.round(completed)}
          aria-valuemin={0}
          aria-valuemax={target}
          aria-label={`${completed} of ${target} credits completed`}
        >
          <div className="creditsFill creditsDone" style={{ width: `${completedPct}%` }} />
          <div className="creditsFill creditsProgress" style={{ width: `${inProgressPct}%` }} />
          {ticks.map((tick) => (
            <span
              key={tick}
              className="creditsTick"
              style={{ left: `${(tick / safeTarget) * 100}%` }}
            >
              <span className="creditsTickLabel">{tick}</span>
            </span>
          ))}
        </div>

        <div className="creditsPercent">{Math.round(completedPct)}%</div>
      </div>

      <p className="creditsRemaining">
        {completed} of {target} credits &middot; {remaining} left
      </p>
    </div>
  );
}
