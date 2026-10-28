import { FormEvent, useCallback, useEffect, useState } from "react";
import HelpTip from "../../shared/components/HelpTip";
import {
  Directory, DirectoryTeam, fetchDirectory, fetchMyJoinRequests, joinTeam, MyJoinRequest, withdrawJoinRequest,
} from "./api";

/** Why a request couldn't be sent, in words. */
const REFUSED: Record<string, string> = {
  not_listed: "That team isn't listed any more.",
  own: "You're already on that team.",
  already: "You've already asked that team.",
  limit: "You have 5 requests waiting. Take one back, or wait for answers.",
  invalid: "That couldn't be sent.",
};

/** Where your request stands, in words. */
const REQUEST_STATES = { pending: "waiting", accepted: "accepted", declined: "declined" } as const;

/**
 * "League directory" (Phase 3 item 9): listed teams to browse and filter by sport, asking to join
 * with a message; your own requests below. Never a member's name.
 */
export default function DirectoryCard({ userId }: { readonly userId: string }) {
  const [directory, setDirectory] = useState<Directory | null>(null);
  const [mine, setMine] = useState<MyJoinRequest[]>([]);
  const [sport, setSport] = useState("");
  const [asking, setAsking] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [found, requests] = await Promise.all([fetchDirectory(userId), fetchMyJoinRequests(userId)]);
      setDirectory(found);
      setMine(requests);
    } catch {
      setDirectory(null);
    }
  }, [userId]);

  useEffect(() => { void load(); }, [load]);

  async function ask(event: FormEvent, team: DirectoryTeam) {
    event.preventDefault();
    setNotice(null);
    try {
      const { status } = await joinTeam(userId, team.team_id, message.trim() || null);
      setNotice(status === "sent" ? `Asked ${team.name}. The captain sees your name and message.` : REFUSED[status]);
      setAsking(null);
      setMessage("");
      await load();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "That couldn't be sent.");
    }
  }

  async function takeBack(request: MyJoinRequest) {
    try {
      await withdrawJoinRequest(userId, request.id);
      await load();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Couldn't take that back.");
    }
  }

  if (!directory) return null;
  const sports = [...new Set(directory.teams.map((t) => t.sport).filter((s): s is string => !!s))].sort();
  const shown = directory.teams.filter((t) => !sport || t.sport === sport);

  return (
    <section className="fitnessCard" aria-label="League directory">
      <div className="fitnessCardHead">
        <h2>League directory</h2>
        <HelpTip label="About the directory">
          Teams their captains listed on campus. Asking to join sends the captain your name and a short
          message; nobody else sees it. Teams with no game in 30 days are greyed. Opens once
          {" "}{directory.floor} teams are listed.
        </HelpTip>
      </div>
      {notice && <p className="small-text" role="status">{notice}</p>}
      {directory.teams.length === 0 ? (
        <p className="small-text muted">Opens once {directory.floor} teams are listed on campus.</p>
      ) : (
        <>
          {sports.length > 1 && (
            <select className="calInput directorySport" value={sport} onChange={(e) => setSport(e.target.value)}
                    aria-label="Sport">
              <option value="">Every sport</option>
              {sports.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          )}
          <ul className="directoryList">
            {shown.map((team) => (
              <li key={team.team_id} className={team.dormant ? "directoryDormant" : undefined}>
                <div>
                  <strong>{team.name}</strong>
                  <span className="small-text muted">
                    {[team.sport, team.level, team.area, `${team.members} on the team`].filter(Boolean).map((part) => ` · ${part}`)}
                    {team.looking && " · looking for players"}
                    {team.dormant && " · no recent games"}
                  </span>
                  {team.blurb && <p className="small-text">{team.blurb}</p>}
                </div>
                {team.mine ? (
                  <span className="small-text muted">Your team</span>
                ) : team.requested ? (
                  <span className="small-text muted">Asked: {REQUEST_STATES[team.requested]}</span>
                ) : asking === team.team_id ? (
                  <form className="directoryAsk" onSubmit={(event) => void ask(event, team)}>
                    <input className="calInput" value={message} maxLength={200} placeholder="A message (optional)"
                           aria-label={`Message for ${team.name}`} onChange={(e) => setMessage(e.target.value)} />
                    <button type="submit" className="calButton calButtonPrimary">Send</button>
                    <button type="button" className="calButton" onClick={() => setAsking(null)}>Cancel</button>
                  </form>
                ) : (
                  <button type="button" className="calButton" onClick={() => setAsking(team.team_id)}>
                    Ask to join
                  </button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      {mine.length > 0 && (
        <div className="directoryMine">
          <h3>Your requests</h3>
          <ul>
            {mine.map((request) => (
              <li key={request.id}>
                <span>{request.team_name} · {REQUEST_STATES[request.status]}</span>
                {request.status === "pending" && (
                  <button type="button" className="courseLinkAdd" onClick={() => void takeBack(request)}>Take back</button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
