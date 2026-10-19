import { FormEvent, useCallback, useEffect, useState } from "react";
import { useAuth } from "../app/auth/AuthContext";
import HelpTip from "../shared/components/HelpTip";
import SharingSection from "../shared/components/SharingSection";
import { shortDate, today } from "../shared/utils/dateUtils";
import {
  Game, GameInput, TeamDetail, TeamSummary, cancelTeamLink, confirmGame, correctGame, createTeam, disputeGame,
  fetchTeam, fetchTeams, leaveTeam, makeTeamLink, recordGame, recordLine, removeGame, removeTeam,
  removeTeamMember, teamInviteLink,
} from "../features/teams/api";
import { useApiRefresh } from "../shared/hooks/useApiRefresh";
import "../styles/teams.css";

/**
 * Fitness (Phase 2 item 11, D26). Today: your teams, their games, and the
 * record. The exertion features of a later phase join it here.
 *
 * Anyone on a team records a game; it counts once someone else confirms it,
 * the captain included. A disputed score shows both and counts for nothing
 * until whoever recorded it corrects it. Only the captain changes who is on
 * the team.
 */
export default function FitnessPage() {
  const { user } = useAuth();
  const [teams, setTeams] = useState<TeamSummary[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [sport, setSport] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!user) return;
    try {
      const next = await fetchTeams(user.id);
      setTeams(next);
      setSelected((current) => current ?? next[0]?.team_id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load your teams");
    }
  }, [user]);

  useEffect(() => { void load(); }, [load]);
  // Catch up when a background refetch finds something new (audit #35).
  useApiRefresh(load);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!user || !name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const made = await createTeam(user.id, name.trim(), sport.trim() || null);
      setName("");
      setSport("");
      setSelected(made.team_id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't make the team");
    } finally {
      setBusy(false);
    }
  }

  if (!user) return null;

  return (
    <div className="container teamsPage">
      <div className="teamsTopbar">
        <h1 className="title">Fitness</h1>
        <HelpTip label="How scores count">
          Anyone on a team can record a game. It counts once someone else on the team confirms it, the
          captain included. If someone disputes it, both scores show and it doesn&rsquo;t count until
          whoever recorded it corrects it.
        </HelpTip>
      </div>
      {error && <p className="calError" role="alert">{error}</p>}

      <div className="teamsGrid">
        <aside className="teamsList" aria-label="Your teams">
          <h2 className="teamsHeading">Teams</h2>
          {teams && teams.length === 0 && (
            <p className="small-text muted">No teams yet. Make one, then send your teammates the link.</p>
          )}
          <ul>
            {(teams ?? []).map((team) => (
              <li key={team.team_id}>
                <button type="button" aria-pressed={selected === team.team_id}
                        className={selected === team.team_id ? "teamCard teamCardActive" : "teamCard"}
                        onClick={() => setSelected(team.team_id)}>
                  <span className="teamCardName">{team.name}</span>
                  <span className="small-text muted">
                    {[team.sport, team.is_captain ? "your team" : `${team.captain_name}'s team`].filter(Boolean).join(" · ")}
                  </span>
                  <span className="teamCardRecord">{recordLine(team.record)}</span>
                </button>
              </li>
            ))}
          </ul>
          <form className="teamsNew" onSubmit={create}>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Team name" maxLength={60}
                   aria-label="New team name" />
            <input value={sport} onChange={(e) => setSport(e.target.value)} placeholder="Sport (optional)" maxLength={30}
                   aria-label="New team sport" />
            <button type="submit" className="calButton calButtonPrimary" disabled={busy || !name.trim()}>New team</button>
          </form>
        </aside>

        {selected && (
          <TeamView key={selected} userId={user.id} teamId={selected}
                    onGone={() => { setSelected(null); void load(); }} onChanged={load} />
        )}
      </div>
    </div>
  );
}

interface ViewProps {
  readonly userId: string;
  readonly teamId: string;
  readonly onGone: () => void;
  readonly onChanged: () => Promise<void>;
}

function TeamView({ userId, teamId, onGone, onChanged }: ViewProps) {
  const [team, setTeam] = useState<TeamDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [ending, setEnding] = useState(false);

  const load = useCallback(async () => {
    try {
      setTeam(await fetchTeam(userId, teamId));
    } catch {
      setTeam(null);
    }
  }, [userId, teamId]);

  useEffect(() => { void load(); }, [load]);
  // Catch up when a background refetch finds something new (audit #35).
  useApiRefresh(load);

  async function act(step: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await step();
      await load();
      await onChanged();
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "That didn't work. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const sharing = useCallback(async () => {
    const detail = await fetchTeam(userId, teamId);
    return { members: detail.members ?? [], link: detail.link, shareable: true, max_members: 30 };
  }, [userId, teamId]);

  if (!team) return <p className="muted" role="status">Loading the team…</p>;
  const r = team.record;

  return (
    <section className="teamView" aria-label={team.name}>
      <header className="teamHeader">
        <h2>{team.name}</h2>
        <p className="small-text muted">
          {[team.sport, team.is_captain ? "You're the captain" : `Captain: ${team.captain_name}`].filter(Boolean).join(" · ")}
          {team.member_names.length > 0 && ` · with ${team.member_names.join(", ")}`}
        </p>
        <p className="teamRecord">
          <strong>{recordLine(r)}</strong>
          <span className="small-text muted"> wins–losses–ties · {r.points_for}–{r.points_against} points</span>
          {r.unconfirmed > 0 && <span className="small-text"> · {r.unconfirmed} waiting to be confirmed</span>}
        </p>
      </header>

      <GameForm submitLabel="Record the game" busy={busy}
                onSubmit={(game) => act(() => recordGame(userId, teamId, game))} />
      {error && <p className="small-text error" role="alert">{error}</p>}

      {team.games.length === 0 ? (
        <p className="small-text muted">No games yet.</p>
      ) : (
        <ul className="gameList">
          {team.games.map((game) => (
            <GameRow key={game.game_id} game={game} isCaptain={team.is_captain} busy={busy}
                     onConfirm={() => act(() => confirmGame(userId, teamId, game.game_id))}
                     onDispute={(ours, theirs) => act(() => disputeGame(userId, teamId, game.game_id, ours, theirs))}
                     onCorrect={(next) => act(() => correctGame(userId, teamId, game.game_id, next))}
                     onRemove={() => act(() => removeGame(userId, teamId, game.game_id))} />
          ))}
        </ul>
      )}

      {team.is_captain ? (
        <>
          <SharingSection
            noun="team"
            load={sharing}
            makeLink={() => makeTeamLink(userId, teamId)}
            cancelLink={() => cancelTeamLink(userId, teamId)}
            removeMember={(memberId) => removeTeamMember(userId, teamId, memberId)}
            linkFor={teamInviteLink}
            notShareable=""
            onChanged={() => { void load(); void onChanged(); }}
            help={<>
              Anyone who joins through your link sees the team, its roster&rsquo;s names and its games, and can
              record, confirm or dispute a game. Only you can rename the team, take someone off, or delete it.
            </>}
          />
          <div className="catalogueActions">
            {ending ? (
              <>
                <span className="small-text">Delete {team.name}, its games and its roster? This can&rsquo;t be undone.</span>
                <button type="button" className="calButton calButtonDanger" disabled={busy}
                        onClick={() => void act(async () => { await removeTeam(userId, teamId); onGone(); })}>
                  Yes, delete
                </button>
                <button type="button" className="calButton" onClick={() => setEnding(false)}>Keep</button>
              </>
            ) : (
              <button type="button" className="courseLinkAdd" onClick={() => setEnding(true)}>Delete this team</button>
            )}
          </div>
        </>
      ) : (
        <div className="catalogueActions">
          {ending ? (
            <>
              <span className="small-text">Leave {team.name}? You&rsquo;d need a new link from {team.captain_name} to rejoin.</span>
              <button type="button" className="calButton calButtonDanger" disabled={busy}
                      onClick={() => void act(async () => { await leaveTeam(userId, teamId); onGone(); })}>
                Leave
              </button>
              <button type="button" className="calButton" onClick={() => setEnding(false)}>Stay</button>
            </>
          ) : (
            <button type="button" className="courseLinkAdd" onClick={() => setEnding(true)}>Leave this team</button>
          )}
        </div>
      )}
    </section>
  );
}

interface FormProps {
  readonly submitLabel: string;
  readonly busy: boolean;
  readonly initial?: GameInput;
  readonly onSubmit: (game: GameInput) => Promise<void>;
  readonly onCancel?: () => void;
}

/** The post-game form: today's date already in, four fields, one button. */
function GameForm({ submitLabel, busy, initial, onSubmit, onCancel }: FormProps) {
  const [playedOn, setPlayedOn] = useState(initial?.played_on ?? today());
  const [opponent, setOpponent] = useState(initial?.opponent ?? "");
  const [ours, setOurs] = useState(initial ? String(initial.our_score) : "");
  const [theirs, setTheirs] = useState(initial ? String(initial.their_score) : "");
  const ready = opponent.trim() !== "" && ours !== "" && theirs !== "";

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready) return;
    await onSubmit({ played_on: playedOn, opponent: opponent.trim(), our_score: Number(ours), their_score: Number(theirs) });
    if (!initial) {
      setOpponent("");
      setOurs("");
      setTheirs("");
    }
  }

  return (
    <form className="gameForm" onSubmit={submit} aria-label={submitLabel}>
      <input type="date" value={playedOn} onChange={(e) => setPlayedOn(e.target.value)} aria-label="Date played" />
      <input value={opponent} onChange={(e) => setOpponent(e.target.value)} placeholder="Opponent" maxLength={60}
             aria-label="Opponent" />
      <input type="number" min={0} max={999} inputMode="numeric" value={ours} onChange={(e) => setOurs(e.target.value)}
             placeholder="Us" aria-label="Our score" />
      <input type="number" min={0} max={999} inputMode="numeric" value={theirs} onChange={(e) => setTheirs(e.target.value)}
             placeholder="Them" aria-label="Their score" />
      <button type="submit" className="calButton calButtonPrimary" disabled={busy || !ready}>{submitLabel}</button>
      {onCancel && <button type="button" className="calButton" onClick={onCancel}>Cancel</button>}
    </form>
  );
}

interface RowProps {
  readonly game: Game;
  readonly isCaptain: boolean;
  readonly busy: boolean;
  readonly onConfirm: () => Promise<void>;
  readonly onDispute: (ours: number, theirs: number) => Promise<void>;
  readonly onCorrect: (game: GameInput) => Promise<void>;
  readonly onRemove: () => Promise<void>;
}

function GameRow({ game, isCaptain, busy, onConfirm, onDispute, onCorrect, onRemove }: RowProps) {
  const [mode, setMode] = useState<"idle" | "dispute" | "correct" | "remove">("idle");
  const [ours, setOurs] = useState(String(game.our_score));
  const [theirs, setTheirs] = useState(String(game.their_score));
  const confirmed = game.confirmed_by_name !== null;
  const disputed = game.disputed_by_name !== null;
  const canConfirm = !game.recorded_by_me && !confirmed && (!disputed || game.disputed_by_me);
  const canDispute = !game.recorded_by_me && !confirmed;
  const canCorrect = game.recorded_by_me && !confirmed;
  const canRemove = (game.recorded_by_me && !confirmed) || isCaptain;

  let status: string;
  if (confirmed) status = `Confirmed by ${game.confirmed_by_name}`;
  else if (disputed) status = `Disputed by ${game.disputed_by_name}, who says ${game.disputed_our}–${game.disputed_their}`;
  else status = `Recorded by ${game.recorded_by_name}; waiting for someone else to confirm`;

  if (mode === "correct") {
    return (
      <li className="gameRow">
        <GameForm submitLabel="Save the correction" busy={busy} onCancel={() => setMode("idle")}
                  initial={{ played_on: game.played_on, opponent: game.opponent, our_score: game.our_score,
                             their_score: game.their_score }}
                  onSubmit={async (next) => { await onCorrect(next); setMode("idle"); }} />
      </li>
    );
  }

  return (
    <li className={`gameRow${confirmed ? " gameRowConfirmed" : ""}${disputed ? " gameRowDisputed" : ""}`}>
      <div className="gameMain">
        <span className="gameScore">{game.our_score}–{game.their_score}</span>
        <span>vs {game.opponent}</span>
        <span className="small-text muted">{shortDate(game.played_on)}</span>
      </div>
      <p className="small-text">{status}</p>
      {mode === "dispute" ? (
        <span className="catalogueActions">
          <span className="small-text">What was it?</span>
          <input type="number" min={0} max={999} value={ours} onChange={(e) => setOurs(e.target.value)} aria-label="Our score, as you saw it" />
          <input type="number" min={0} max={999} value={theirs} onChange={(e) => setTheirs(e.target.value)} aria-label="Their score, as you saw it" />
          <button type="button" className="calButton calButtonPrimary" disabled={busy}
                  onClick={() => void onDispute(Number(ours), Number(theirs)).then(() => setMode("idle"))}>
            Send
          </button>
          <button type="button" className="calButton" onClick={() => setMode("idle")}>Cancel</button>
        </span>
      ) : mode === "remove" ? (
        <span className="catalogueActions">
          <span className="small-text">Delete this game?</span>
          <button type="button" className="calButton calButtonDanger" disabled={busy}
                  onClick={() => void onRemove().then(() => setMode("idle"))}>
            Yes, delete
          </button>
          <button type="button" className="calButton" onClick={() => setMode("idle")}>Keep</button>
        </span>
      ) : (
        <span className="catalogueActions">
          {canConfirm && (
            <button type="button" className="calButton calButtonPrimary" disabled={busy} onClick={() => void onConfirm()}>
              {game.disputed_by_me ? "Confirm it after all" : "Confirm"}
            </button>
          )}
          {canDispute && (
            <button type="button" className="calButton" disabled={busy} onClick={() => setMode("dispute")}>Dispute</button>
          )}
          {canCorrect && (
            <button type="button" className="calButton" disabled={busy} onClick={() => setMode("correct")}>Correct</button>
          )}
          {canRemove && (
            <button type="button" className="courseLinkAdd" disabled={busy} onClick={() => setMode("remove")}>Delete</button>
          )}
        </span>
      )}
    </li>
  );
}
