import { UserGradeDashboard } from "../types";

interface SemesterSummaryProps {
  readonly summary: UserGradeDashboard | null;
}

export default function SemesterSummary({ summary }: SemesterSummaryProps) {
  if (!summary) return null;

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
    </div>
  );
}
