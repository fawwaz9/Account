import { useEffect, useState } from "react";
import { applyOutline, fetchOutline, offerOutline, withdrawOutlineOffer } from "../api";
import { OutlineStatus } from "../types";
import HelpTip from "../../../shared/components/HelpTip";

/** The course, a refetch counter, and what to do once an outline has filled it. */
interface CourseOutlineProps {
  readonly userId: string;
  readonly courseId: string;
  readonly nonce: number;
  /** Called after "Use it" fills the course, so the page reloads its grades. */
  readonly onApplied: () => void;
}

/** Where your offer's review stands, in words. */
const OFFER_STATES: Record<"pending" | "accepted" | "rejected", string> = {
  pending: "Offered to classmates, waiting for review.",
  accepted: "Shared: classmates in this course and term can use it.",
  rejected: "Not shared after review.",
};

/**
 * Shared course outlines (Phase 3 item 2): fill an empty course from a reviewed one, or offer
 * this course's outline to classmates. Silent when neither is possible.
 */
export default function CourseOutline({ userId, courseId, nonce, onApplied }: CourseOutlineProps) {
  const [status, setStatus] = useState<OutlineStatus | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchOutline(userId, courseId)
      .then((found) => { if (!cancelled) setStatus(found); })
      .catch(() => { if (!cancelled) setStatus(null); });
    return () => { cancelled = true; };
  }, [userId, courseId, nonce]);

  async function act(action: () => Promise<OutlineStatus | null>, after?: () => void) {
    setBusy(true);
    setError(null);
    try {
      const next = await action();
      setStatus(next ?? (await fetchOutline(userId, courseId)));
      after?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not do that");
    } finally {
      setBusy(false);
    }
  }

  if (!status) return null;
  const { shared, offer } = status;
  if (!status.can_apply && !status.can_offer && !offer) return null;

  return (
    <section className="courseOutline" aria-label="Course outline">
      {status.can_apply && shared ? (
        <>
          <p className="courseOutlineLine">
            A reviewed outline for this course and term: {Object.keys(shared.outline.weights).length} categories,{" "}
            {shared.outline.assessments.length} assessments, no marks.
          </p>
          {previewing && (
            <ul className="courseOutlineList" aria-label="Outline">
              {Object.entries(shared.outline.weights).map(([category, weight]) => (
                <li key={category}>{category}: {weight}%</li>
              ))}
              {shared.outline.assessments.map((item, index) => (
                <li key={`${item.name}-${index}`}>
                  {item.name} · {item.category}{item.due_date ? ` · due ${item.due_date}` : ""}
                </li>
              ))}
            </ul>
          )}
          <div className="courseOutlineActions">
            <button type="button" className="calButton" onClick={() => setPreviewing((was) => !was)}>
              {previewing ? "Hide" : "Preview"}
            </button>
            <button type="button" className="calButton calButtonPrimary" disabled={busy}
              onClick={() => void act(() => applyOutline(userId, courseId), onApplied)}>
              Use it
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="courseOutlineLine">
            {offer ? OFFER_STATES[offer.status] : "Share this course's outline with classmates?"}
            <HelpTip label="About sharing an outline">
              Your categories, weights and assessment names and dates, never your marks. It reaches
              classmates in the same course and term only after review, and they can change anything.
            </HelpTip>
          </div>
          <div className="courseOutlineActions">
            {status.can_offer && (
              <button type="button" className="calButton" disabled={busy}
                onClick={() => void act(() => offerOutline(userId, courseId))}>
                {offer ? "Offer again" : "Offer outline"}
              </button>
            )}
            {offer && offer.status === "pending" && (
              <button type="button" className="calButton" disabled={busy}
                onClick={() => void act(async () => { await withdrawOutlineOffer(userId, courseId); return null; })}>
                Take back
              </button>
            )}
          </div>
        </>
      )}
      {error && <p className="calError" role="alert">{error}</p>}
    </section>
  );
}
