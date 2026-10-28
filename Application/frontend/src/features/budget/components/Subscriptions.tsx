import { useEffect, useState } from "react";
import { confirmSubscription, fetchSubscriptions } from "../api";
import { SubscriptionCandidate } from "../types";
import { formatMoney } from "../money";
import { useAuth } from "../../../app/auth/AuthContext";
import { dueLabel } from "../../../shared/utils/dateUtils";

/** Props for the subscription audit. */
interface SubscriptionsProps {
  /** Bumped by the page when something changes, to refetch. */
  readonly nonce: number;
  /** Called after a confirm, so the page reloads its standing instructions. */
  readonly onConfirmed: () => void;
}

/** Display label per cadence. */
const CADENCE_LABEL: Record<SubscriptionCandidate["cadence"], string> = {
  weekly: "Every week",
  fortnightly: "Every two weeks",
  monthly: "Every month",
};

/**
 * Repeating charges with no standing instruction behind them, each confirmable as one.
 * Re-derived from the ledger on every fetch, so a card cannot be dismissed, only confirmed.
 */
export default function Subscriptions({ nonce, onConfirmed }: SubscriptionsProps) {
  const { user } = useAuth();
  const [found, setFound] = useState<SubscriptionCandidate[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Per card: the last date it runs. Empty means ongoing. Asked because a rule
  // with no end projects forever, and a lease or a term-length subscription
  // has a natural one -- left out, it quietly corrupts every forecast
  // (account-vision.md §13.9).
  const [until, setUntil] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!user) return;

    let cancelled = false;
    fetchSubscriptions(user.id)
      .then((rows) => { if (!cancelled) setFound(rows); })
      .catch(() => { if (!cancelled) setFound([]); });

    return () => { cancelled = true; };
  }, [user, nonce]);

  if (found.length === 0) return null;

  async function handleConfirm(candidate: SubscriptionCandidate) {
    if (!user) return;

    setBusy(candidate.description);
    setError(null);
    try {
      await confirmSubscription(user.id, candidate, until[keyOf(candidate)] || null);
      setFound((current) => current.filter((row) => row !== candidate));
      onConfirmed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not confirm that subscription");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="subsSection">
      <div className="sectionHeading">
        <h2>Subscriptions found</h2>
        <span className="small-text muted">
          {found.length} {found.length === 1 ? "charge repeats" : "charges repeat"} with no
          standing instruction behind them
        </span>
      </div>

      {error && <p className="calError">{error}</p>}

      <ul className="subsList">
        {found.map((candidate) => (
          <li key={keyOf(candidate)} className="subsCard">
            <div className="subsHead">
              <span className="subsName">{candidate.description}</span>
              <span className="subsAmount">{formatMoney(candidate.median_amount)}</span>
            </div>

            <span className="small-text muted">
              {CADENCE_LABEL[candidate.cadence]} · charged {candidate.occurrences.length} times ·
              last on {dueLabel(candidate.last_seen)}
            </span>

            <div className="subsActions">
              <span className="small-text muted">
                Next expected {dueLabel(candidate.next_expected_on)}
              </span>
              <label className="subsUntil">
                <span className="small-text muted">Until</span>
                <input
                  className="--input"
                  type="date"
                  min={candidate.next_expected_on}
                  value={until[keyOf(candidate)] ?? ""}
                  onChange={(event) => setUntil({ ...until, [keyOf(candidate)]: event.target.value })}
                  disabled={busy !== null}
                  aria-label={`${candidate.description} runs until`}
                />
                <span className="small-text muted">
                  {until[keyOf(candidate)] ? "" : "ongoing"}
                </span>
              </label>
              <button
                type="button"
                className="calButton calButtonPrimary"
                onClick={() => handleConfirm(candidate)}
                disabled={busy !== null}
              >
                {busy === candidate.description ? "Confirming…" : "Make it a standing instruction"}
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Stable key for a candidate: its first charge's id. */
function keyOf(candidate: SubscriptionCandidate): string {
  return candidate.occurrences[0]?.transaction_id ?? candidate.description;
}
