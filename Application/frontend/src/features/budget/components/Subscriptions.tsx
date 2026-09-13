import { useEffect, useState } from "react";
import { confirmSubscription, fetchSubscriptions } from "../api";
import { SubscriptionCandidate } from "../types";
import { formatMoney } from "../money";
import { useAuth } from "../../../app/auth/AuthContext";
import { dueLabel } from "../../../shared/utils/dateUtils";

interface SubscriptionsProps {
  readonly nonce: number;
  readonly onConfirmed: () => void;
}

const CADENCE_LABEL: Record<SubscriptionCandidate["cadence"], string> = {
  weekly: "Every week",
  fortnightly: "Every two weeks",
  monthly: "Every month",
};

/**
 * Recurring charges nobody told the app about.
 *
 * Nothing here is stored -- every fetch re-derives the pattern from the
 * ledger, which is also why there is no way to dismiss a card without acting
 * on it. Confirming tags the charges that made the pattern with the new
 * instruction's id, so the same history stops qualifying as a finding.
 */
export default function Subscriptions({ nonce, onConfirmed }: SubscriptionsProps) {
  const { user } = useAuth();
  const [found, setFound] = useState<SubscriptionCandidate[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
      await confirmSubscription(user.id, candidate);
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
          <li key={candidate.occurrences[0]?.transaction_id ?? candidate.description} className="subsCard">
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
