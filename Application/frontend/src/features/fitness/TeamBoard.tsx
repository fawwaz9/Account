import { useCallback, useEffect, useState } from "react";
import HelpTip from "../../shared/components/HelpTip";
import { useAuth } from "../../app/auth/AuthContext";
import { updatePreferences } from "../../services/currentUserClient";
import { fetchTeamBoard, TeamBoard as Board } from "./api";

/**
 * "This week" on a team (Phase 3 item 8): teammates' activity points, for those who chose to
 * appear, seen only once you have too; the switch to opt in or out sits beside it.
 */
export default function TeamBoard({ userId, teamId }: { readonly userId: string; readonly teamId: string }) {
  const { refreshUser } = useAuth();
  const [board, setBoard] = useState<Board | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setBoard(await fetchTeamBoard(userId, teamId));
    } catch {
      setBoard(null);
    }
  }, [userId, teamId]);

  useEffect(() => { void load(); }, [load]);

  async function optIn(next: boolean) {
    setError(null);
    try {
      await updatePreferences(userId, { leaderboard_opt_in: next });
      await refreshUser();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save that");
    }
  }

  if (!board) return null;

  return (
    <div className="teamBoard" aria-label="This week">
      <div className="fitnessCardHead">
        <h3>This week</h3>
        <HelpTip label="About team boards">
          Activity points this week for teammates who chose to show theirs, seen only by teammates who
          have too. Your points also count toward this team&rsquo;s place on the campus board if its
          captain lists it. Off until you turn it on.
        </HelpTip>
      </div>
      <label className="settingsToggle">
        <input type="checkbox" checked={board.opted_in} onChange={(e) => void optIn(e.target.checked)} />
        Show my points on team boards
      </label>
      {error && <p className="calError" role="alert">{error}</p>}
      {board.opted_in && (
        board.rows.length === 0 ? (
          <p className="small-text muted">No points logged this week yet.</p>
        ) : (
          <ol className="teamBoardList">
            {board.rows.map((row) => (
              <li key={row.name} className={row.is_me ? "teamBoardMe" : undefined}>
                <span>{row.name}{row.is_me ? " (you)" : ""}</span>
                <strong>{row.points}</strong>
              </li>
            ))}
          </ol>
        )
      )}
    </div>
  );
}
