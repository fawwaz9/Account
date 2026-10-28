import { useEffect, useState } from "react";
import HelpTip from "../../shared/components/HelpTip";
import { CampusBoard, fetchCampusBoard } from "./api";

/** "Campus board" (Phase 3 item 8): listed teams ranked by this week's points; never a person. */
export default function CampusBoardCard({ userId }: { readonly userId: string }) {
  const [board, setBoard] = useState<CampusBoard | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchCampusBoard(userId)
      .then((found) => { if (!cancelled) setBoard(found); })
      .catch(() => { if (!cancelled) setBoard(null); });
    return () => { cancelled = true; };
  }, [userId]);

  if (!board) return null;

  return (
    <section className="fitnessCard" aria-label="Campus board">
      <div className="fitnessCardHead">
        <h2>Campus board</h2>
        <HelpTip label="About the campus board">
          Teams their captains listed, ranked by the points their players chose to share this week,
          counted once a day. Team names only, never a person. Opens once {board.floor} teams are listed.
        </HelpTip>
      </div>
      {board.teams.length === 0 ? (
        <p className="small-text muted">Opens once {board.floor} teams are listed on campus.</p>
      ) : (
        <ol className="campusBoardList">
          {board.teams.map((team, index) => (
            <li key={`${team.team_name}-${index}`}>
              <span>{team.team_name}{team.sport && <span className="small-text muted"> · {team.sport}</span>}</span>
              <strong>{team.points}</strong>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
