import { UserGradeDashboard } from "../types";
import HelpTip from "../../../shared/components/HelpTip";

/** The grades dashboard summary, or null while it loads. */
interface SemesterSummaryProps {
  readonly summary: UserGradeDashboard | null;
}

/** Semester and cumulative averages, plus CGPA when the GPA scale is on; nothing while loading. */
export default function SemesterSummary({ summary }: SemesterSummaryProps) {
  if (!summary) return null;

  // `!= null` on purpose: an API older than this page omits the fields entirely,
  // and undefined must hide the pair just as null does.
  const withTerm = summary.cumulative_average_including_term;
  const cgpaWithTerm = summary.cgpa_including_term;

  return (
    <div className="summaryPanel">
      <div className="summaryStat">
        <span className="summaryStatLabel">Semester Average</span>
        <span className="summaryStatValue">{summary.semester_average}%</span>
      </div>

      <div className="summaryStat">
        <span className="summaryStatLabel">Cumulative Average</span>
        <span className="summaryStatValue">{summary.cumulative_average}%</span>
      </div>

      {/* Null when the GPA scale is switched off in settings. UBC does not put
          a GPA on transcripts, so showing one is opt-in. */}
      {summary.cgpa !== null && (
        <div className="summaryStat">
          <span className="summaryStatLabel">CGPA</span>
          <span className="summaryStatValue summaryStatBoxed">{summary.cgpa}</span>
        </div>
      )}

      {/* The second pair (Phase 4 D5): the official figures count finished
          courses only, so marks entered this term never move them. Absent when
          no current course has a mark, since it would only repeat them. */}
      {withTerm != null && (
        <div className="summaryIncluding" aria-label="Including this term">
          <div className="labelWithTip">
            <span className="summaryIncludingLabel">Including this term</span>
            <HelpTip label="What including this term means">
              Each course this term counts at its running average, the figure the
              Semester Average uses, with its credits. The official figures above
              count only courses with a final grade.
            </HelpTip>
          </div>

          <div className="summaryStat">
            <span className="summaryStatLabel">Cumulative Average</span>
            <span className="summaryStatValue summaryStatSecondary">{withTerm}%</span>
          </div>

          {cgpaWithTerm != null && (
            <div className="summaryStat">
              <span className="summaryStatLabel">CGPA</span>
              <span className="summaryStatValue summaryStatSecondary summaryStatBoxed">{cgpaWithTerm}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
