import { FormEvent, useEffect, useState } from "react";
import HelpTip from "../../shared/components/HelpTip";
import { fetchGymBuddies, GymBuddies, saveGymBuddy } from "./api";

/**
 * "Gym buddy" (Phase 3 item 13): say you're looking for someone to train with, and see which
 * partners and teammates are too. Only connections, and only while you're visible yourself.
 */
export default function GymBuddy({ userId }: { readonly userId: string }) {
  const [state, setState] = useState<GymBuddies | null>(null);
  const [times, setTimes] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function show(next: GymBuddies) {
    setState(next);
    setTimes(next.times ?? "");
    setNote(next.note ?? "");
  }

  useEffect(() => {
    let cancelled = false;
    fetchGymBuddies(userId)
      .then((found) => { if (!cancelled) show(found); })
      .catch(() => { if (!cancelled) setState(null); });
    return () => { cancelled = true; };
  }, [userId]);

  async function save(looking: boolean, event?: FormEvent) {
    event?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      show(await saveGymBuddy(userId, looking, times.trim() || null, note.trim() || null));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save that");
    } finally {
      setBusy(false);
    }
  }

  if (!state) return null;

  return (
    <section className="fitnessCard" aria-label="Gym buddy">
      <div className="fitnessCardHead">
        <h2>Gym buddy</h2>
        <HelpTip label="Who sees this">
          Only your accountability partners and teammates, and only those looking too. Nobody else ever
          sees it, and you see them only while you&rsquo;re looking yourself.
        </HelpTip>
      </div>
      <form className="gymBuddyForm" onSubmit={(event) => void save(true, event)}>
        <input className="calInput" value={times} onChange={(e) => setTimes(e.target.value)} maxLength={80}
               placeholder="When you could go" aria-label="When you could go" />
        <input className="calInput" value={note} onChange={(e) => setNote(e.target.value)} maxLength={120}
               placeholder="Anything else (optional)" aria-label="Anything else" />
        <div className="gymBuddyActions">
          <button type="submit" className="calButton calButtonPrimary" disabled={busy}>
            {state.looking ? "Update" : "I'm looking"}
          </button>
          {state.looking && (
            <button type="button" className="calButton" disabled={busy} onClick={() => void save(false)}>
              Stop looking
            </button>
          )}
        </div>
      </form>
      {error && <p className="calError" role="alert">{error}</p>}
      {state.looking && (
        state.buddies.length === 0 ? (
          <p className="small-text muted">None of your partners or teammates is looking right now.</p>
        ) : (
          <ul className="gymBuddyList" aria-label="Also looking">
            {state.buddies.map((buddy) => (
              <li key={`${buddy.name}-${buddy.via}`}>
                <strong>{buddy.name}</strong>
                <span className="small-text muted"> · {buddy.via}</span>
                {buddy.times && <span> · {buddy.times}</span>}
                {buddy.note && <span className="small-text muted"> · {buddy.note}</span>}
              </li>
            ))}
          </ul>
        )
      )}
    </section>
  );
}
