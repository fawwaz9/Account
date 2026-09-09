import { useNavigate } from "react-router-dom";
import { AttentionItem, AttentionKind } from "../types";

interface AttentionPanelProps {
  readonly items: readonly AttentionItem[];
  readonly userId: string | undefined;
}

const LABELS: Record<AttentionKind, string> = {
  missing_final: "Missing final",
  below_target: "Below target",
  weight_problem: "Check weights",
};

/**
 * Things worth acting on. Ordered by the API, most actionable first: a
 * finished course with no final drops silently out of your cumulative, so it
 * leads.
 */
export default function AttentionPanel({ items, userId }: AttentionPanelProps) {
  const navigate = useNavigate();

  return (
    <section className="attentionPanel">
      <h3 className="attentionTitle">Attention</h3>

      {items.length === 0 ? (
        <p className="small-text muted">Nothing needs attention.</p>
      ) : (
        <ul className="attentionList">
          {items.map((item) => (
            <li key={`${item.kind}-${item.course_id}-${item.message}`}>
              <button
                type="button"
                className="attentionItem"
                onClick={() => userId && navigate(`/grades/courses/${item.course_id}`)}
              >
                <span className={`attentionTag attentionTag--${item.kind}`}>
                  {LABELS[item.kind]}
                </span>
                <span className="attentionBody">
                  <span className="attentionCourse">{item.course_code}</span>
                  <span className="small-text muted">{item.message}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
