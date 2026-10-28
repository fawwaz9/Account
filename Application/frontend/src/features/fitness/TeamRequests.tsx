import { useCallback, useEffect, useState } from "react";
import { answerJoinRequest, fetchTeamJoinRequests, TeamJoinRequest } from "./api";

/**
 * Requests to join a team its captain listed (Phase 3 item 9): who asked and what they said,
 * with Accept and Decline. Silent when nobody has asked.
 */
export default function TeamRequests({ userId, teamId, onChanged }: {
  readonly userId: string;
  readonly teamId: string;
  /** After an accept, so the roster reloads. */
  readonly onChanged: () => void;
}) {
  const [requests, setRequests] = useState<TeamJoinRequest[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setRequests(await fetchTeamJoinRequests(userId, teamId));
    } catch {
      setRequests([]);
    }
  }, [userId, teamId]);

  useEffect(() => { void load(); }, [load]);

  async function answer(request: TeamJoinRequest, accept: boolean) {
    setError(null);
    try {
      const { status } = await answerJoinRequest(userId, request.request_id, accept);
      if (status === "full") setError("The team is full.");
      else if (status === "invalid") setError("That request is no longer waiting.");
      await load();
      if (status === "accepted") onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't answer that");
    }
  }

  if (requests.length === 0 && !error) return null;

  return (
    <div className="teamRequests" aria-label="Requests to join">
      <h3>Asking to join</h3>
      {error && <p className="calError" role="alert">{error}</p>}
      <ul>
        {requests.map((request) => (
          <li key={request.request_id}>
            <span>
              <strong>{request.requester_name}</strong>
              {request.message && <span className="small-text muted"> · {request.message}</span>}
            </span>
            <span className="teamRequestActions">
              <button type="button" className="calButton calButtonPrimary"
                      onClick={() => void answer(request, true)}>Accept</button>
              <button type="button" className="calButton" onClick={() => void answer(request, false)}>Decline</button>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
