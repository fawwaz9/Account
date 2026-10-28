"""Cross-user steps for teams and their games on the Fitness page.

On Postgres each function calls its `SECURITY DEFINER` twin in `rls.FUNCTION_SQL`,
keyed on the session's acting user; on SQLite a plain query gives the same answer
for the `user_id` argument. "On the team" means the captain or a member, while the
captain's account is not being deleted, and every game write goes through here, the
captain's included.
"""
import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app._database.models import (
    DIRECTORY_FLOOR, MAX_PENDING_REQUESTS, MAX_TEAM_MEMBERS, ActivityModel, GameModel, TeamInviteModel,
    TeamJoinRequestModel, TeamMemberModel, TeamModel, UserModel, utc_now,
)


def _is_postgres(db: Session) -> bool:
    """Return True when the session is bound to a Postgres database."""
    return db.get_bind().dialect.name == "postgresql"


@dataclass(frozen=True)
class TeamInvitePreview:
    """What a live team link reveals before it is accepted.

    Attributes:
        captain_name: The captain's display name.
        team_name: The team's name.
        sport: The team's sport, or None.
    """
    captain_name: str
    team_name: str
    sport: str | None


@dataclass(frozen=True)
class MemberTeam:
    """A team the caller plays on as a member, as the definer function reports it.

    Attributes:
        team_id: The team's id.
        team_name: The team's name.
        sport: The team's sport, or None.
        captain_name: The captain's name, as copied when the caller joined.
        member_names: Every member's copied name, in joining order.
    """
    team_id: uuid.UUID
    team_name: str
    sport: str | None
    captain_name: str
    member_names: list[str]


@dataclass(frozen=True)
class Game:
    """One game as a player on the team sees it: names, never other players' ids.

    Attributes:
        game_id: The game's id.
        played_on: Date of the game.
        opponent: Opponent's name.
        our_score: The team's score.
        their_score: The opponent's score.
        recorded_by_name: Name of the player who recorded it.
        recorded_by_me: Whether the caller recorded it.
        confirmed_by_name: Name of the player who confirmed it, or None while
            unconfirmed.
        confirmed_at: When it was confirmed (naive UTC), or None.
        disputed_by_name: Name of the player disputing it, or None.
        disputed_by_me: Whether the caller is the one disputing it.
        disputed_our: The disputed version of our score, or None.
        disputed_their: The disputed version of their score, or None.
    """
    game_id: uuid.UUID
    played_on: date
    opponent: str
    our_score: int
    their_score: int
    recorded_by_name: str
    recorded_by_me: bool
    confirmed_by_name: str | None
    confirmed_at: datetime | None
    disputed_by_name: str | None
    disputed_by_me: bool
    disputed_our: int | None
    disputed_their: int | None


def _live(db: Session, user_id: uuid.UUID) -> UserModel | None:
    """Return the user if their account exists and is not being deleted, else None."""
    user = db.get(UserModel, user_id)
    return user if user is not None and user.deleted_at is None else None


def _on_team(db: Session, user_id: uuid.UUID, team_id: uuid.UUID) -> TeamModel | None:
    """Return the team if the caller is on it and its captain is live, else None."""
    team = db.get(TeamModel, team_id)
    if team is None or _live(db, team.user_id) is None:
        return None
    if team.user_id == user_id:
        return team
    member = db.query(TeamMemberModel).filter_by(team_id=team_id, member_id=user_id).first()
    return team if member is not None else None


def _scores_ok(*scores) -> bool:
    """Return True when every score is present and between 0 and 999."""
    return all(s is not None and 0 <= s <= 999 for s in scores)


def _opponent_ok(opponent: str | None) -> bool:
    """Return True when the opponent's name, stripped, is 1-60 characters."""
    return 1 <= len((opponent or "").strip()) <= 60


def _live_invite(db: Session, token_hash: str):
    """Return the unrevoked, unexpired team link with this token hash, or None."""
    return (
        db.query(TeamInviteModel)
        .filter(TeamInviteModel.token_hash == token_hash, TeamInviteModel.revoked_at.is_(None),
                TeamInviteModel.expires_at > utc_now())
        .first()
    )


def invite_preview(db: Session, user_id: uuid.UUID, token_hash: str) -> TeamInvitePreview | None:
    """Return what a team link shows: the captain's name, the team's name and its sport.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.
        token_hash: SHA-256 hex digest of the link's token.

    Returns:
        The preview, or None when the link is unknown, revoked or expired, or the
        captain's account is being deleted.
    """
    if _is_postgres(db):
        row = db.execute(text("SELECT * FROM account_team_invite_preview(:h)"), {"h": token_hash}).first()
        return TeamInvitePreview(row.captain_name, row.team_name, row.sport) if row else None
    invite = _live_invite(db, token_hash)
    team = db.get(TeamModel, invite.team_id) if invite else None
    captain = _live(db, team.user_id) if team else None
    return TeamInvitePreview(captain.name, team.name, team.sport) if captain else None


def accept_invite(db: Session, user_id: uuid.UUID, token_hash: str) -> str:
    """Join a team through its link, adding the caller as a member.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.
        token_hash: SHA-256 hex digest of the link's token.

    Returns:
        "accepted"; "invalid" when the link is unusable or either account is being
        deleted; "own" for the captain; "already" for an existing member; "full" once
        the team has `MAX_TEAM_MEMBERS` members.

    Note:
        Commits.
    """
    if _is_postgres(db):
        status = db.execute(text("SELECT account_accept_team_invite(:h)"), {"h": token_hash}).scalar()
        db.commit()
        return status
    invite = _live_invite(db, token_hash)
    team = db.get(TeamModel, invite.team_id) if invite else None
    if team is None:
        return "invalid"
    if team.user_id == user_id:
        return "own"
    me, captain = _live(db, user_id), _live(db, team.user_id)
    if me is None or captain is None:
        return "invalid"
    members = db.query(TeamMemberModel).filter(TeamMemberModel.team_id == team.id)
    if members.filter(TeamMemberModel.member_id == user_id).first() is not None:
        return "already"
    if members.count() >= MAX_TEAM_MEMBERS:
        return "full"
    db.add(TeamMemberModel(id=uuid.uuid4(), team_id=team.id, member_id=user_id, member_name=me.name,
                           owner_name=captain.name, joined_at=utc_now()))
    db.commit()
    return "accepted"


def member_teams(db: Session, user_id: uuid.UUID) -> list[MemberTeam]:
    """Return the teams the caller plays on as a member; captains read their own.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.

    Returns:
        One `MemberTeam` per membership whose captain is live; empty when there are
        none.
    """
    if _is_postgres(db):
        rows = db.execute(text("SELECT * FROM account_my_teams()")).all()
        return [MemberTeam(r.team_id, r.team_name, r.sport, r.captain_name, list(r.member_names or [])) for r in rows]
    out = []
    for membership in db.query(TeamMemberModel).filter(TeamMemberModel.member_id == user_id):
        team = db.get(TeamModel, membership.team_id)
        if team is None or _live(db, team.user_id) is None:
            continue
        names = [m.member_name for m in sorted(
            db.query(TeamMemberModel).filter(TeamMemberModel.team_id == team.id),
            key=lambda m: (m.joined_at, m.member_name))]
        out.append(MemberTeam(team.id, team.name, team.sport, membership.owner_name, names))
    return out


def games(db: Session, user_id: uuid.UUID, team_id: uuid.UUID) -> list[Game]:
    """Return a team's games for anyone on it, newest first.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.
        team_id: The team.

    Returns:
        The games by date then recording time, newest first; empty when the caller is
        not on the team.
    """
    if _is_postgres(db):
        rows = db.execute(text("SELECT * FROM account_team_games(:t)"), {"t": team_id}).all()
        return [Game(**r._mapping) for r in rows]
    if _on_team(db, user_id, team_id) is None:
        return []
    rows = (db.query(GameModel).filter(GameModel.team_id == team_id)
            .order_by(GameModel.played_on.desc(), GameModel.created_at.desc()).all())
    return [Game(g.id, g.played_on, g.opponent, g.our_score, g.their_score, g.recorded_by_name,
                 g.recorded_by == user_id, g.confirmed_by_name, g.confirmed_at, g.disputed_by_name,
                 g.disputed_by == user_id, g.disputed_our, g.disputed_their) for g in rows]


def record_game(db: Session, user_id: uuid.UUID, team_id: uuid.UUID, played_on: date, opponent: str,
                ours: int, theirs: int) -> uuid.UUID | None:
    """Record a game for a team the caller is on; it counts once someone else confirms.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.
        team_id: The team.
        played_on: Date of the game; required.
        opponent: Opponent's name; stripped, then 1-60 characters.
        ours: The team's score, 0-999.
        theirs: The opponent's score, 0-999.

    Returns:
        The new game's id, or None when the caller is not on the team or a value is
        invalid.

    Note:
        Commits.
    """
    if _is_postgres(db):
        new_id = db.execute(text("SELECT account_record_team_game(:t, :d, :o, :a, :b)"),
                            {"t": team_id, "d": played_on, "o": opponent, "a": ours, "b": theirs}).scalar()
        db.commit()
        return new_id
    if (_on_team(db, user_id, team_id) is None or played_on is None or not _opponent_ok(opponent)
            or not _scores_ok(ours, theirs)):
        return None
    me = db.get(UserModel, user_id)
    game = GameModel(id=uuid.uuid4(), team_id=team_id, played_on=played_on, opponent=opponent.strip(),
                     our_score=ours, their_score=theirs, recorded_by=user_id, recorded_by_name=me.name,
                     created_at=utc_now())
    db.add(game)
    db.commit()
    return game.id


def _game_on_team(db: Session, user_id: uuid.UUID, game_id: uuid.UUID) -> GameModel | None:
    """Return the game if the caller is on its team, else None."""
    game = db.get(GameModel, game_id)
    if game is None or _on_team(db, user_id, game.team_id) is None:
        return None
    return game


def _clear_dispute(game: GameModel) -> None:
    """Clear every dispute field on a game."""
    game.disputed_by = game.disputed_by_name = game.disputed_our = game.disputed_their = None


def confirm_game(db: Session, user_id: uuid.UUID, game_id: uuid.UUID) -> bool:
    """Confirm another player's unconfirmed game, withdrawing the caller's own dispute.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.
        game_id: The game.

    Returns:
        True if confirmed; False for the game's recorder, a game already confirmed, a
        game disputed by someone else, or a caller not on the team.

    Note:
        Commits.
    """
    if _is_postgres(db):
        done = bool(db.execute(text("SELECT account_confirm_team_game(:g)"), {"g": game_id}).scalar())
        db.commit()
        return done
    game = _game_on_team(db, user_id, game_id)
    if (game is None or game.recorded_by == user_id or game.confirmed_by is not None
            or (game.disputed_by is not None and game.disputed_by != user_id)):
        return False
    game.confirmed_by, game.confirmed_by_name, game.confirmed_at = user_id, db.get(UserModel, user_id).name, utc_now()
    _clear_dispute(game)
    db.commit()
    return True


def dispute_game(db: Session, user_id: uuid.UUID, game_id: uuid.UUID, ours: int, theirs: int) -> bool:
    """Dispute another player's unconfirmed game with the scores the caller believes.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.
        game_id: The game.
        ours: The disputed team score, 0-999.
        theirs: The disputed opponent score, 0-999.

    Returns:
        True if the dispute was recorded; False for the recorder, a confirmed game,
        invalid scores or a caller not on the team.

    Note:
        Commits. A game holds one dispute, so a later dispute replaces an earlier one.
    """
    if _is_postgres(db):
        done = bool(db.execute(text("SELECT account_dispute_team_game(:g, :a, :b)"),
                               {"g": game_id, "a": ours, "b": theirs}).scalar())
        db.commit()
        return done
    game = _game_on_team(db, user_id, game_id)
    if game is None or game.recorded_by == user_id or game.confirmed_by is not None or not _scores_ok(ours, theirs):
        return False
    game.disputed_by, game.disputed_by_name = user_id, db.get(UserModel, user_id).name
    game.disputed_our, game.disputed_their = ours, theirs
    db.commit()
    return True


def correct_game(db: Session, user_id: uuid.UUID, game_id: uuid.UUID, played_on: date, opponent: str,
                 ours: int, theirs: int) -> bool:
    """Let a game's recorder correct it while unconfirmed, clearing any dispute.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.
        game_id: The game.
        played_on: Corrected date; required.
        opponent: Corrected opponent; stripped, then 1-60 characters.
        ours: Corrected team score, 0-999.
        theirs: Corrected opponent score, 0-999.

    Returns:
        True if corrected; False when the caller is not the recorder, the game is
        confirmed, or a value is invalid.

    Note:
        Commits.
    """
    if _is_postgres(db):
        done = bool(db.execute(text("SELECT account_correct_team_game(:g, :d, :o, :a, :b)"),
                               {"g": game_id, "d": played_on, "o": opponent, "a": ours, "b": theirs}).scalar())
        db.commit()
        return done
    game = _game_on_team(db, user_id, game_id)
    if (game is None or game.recorded_by != user_id or game.confirmed_by is not None or played_on is None
            or not _opponent_ok(opponent) or not _scores_ok(ours, theirs)):
        return False
    game.played_on, game.opponent, game.our_score, game.their_score = played_on, opponent.strip(), ours, theirs
    _clear_dispute(game)
    db.commit()
    return True


def delete_game(db: Session, user_id: uuid.UUID, game_id: uuid.UUID) -> bool:
    """Delete a game: the recorder while it is unconfirmed, or the captain at any time.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.
        game_id: The game.

    Returns:
        True if deleted; False when the caller may not delete it.

    Note:
        Commits.
    """
    if _is_postgres(db):
        done = bool(db.execute(text("SELECT account_delete_team_game(:g)"), {"g": game_id}).scalar())
        db.commit()
        return done
    game = _game_on_team(db, user_id, game_id)
    if game is None:
        return False
    captain = db.get(TeamModel, game.team_id).user_id == user_id
    if not captain and (game.recorded_by != user_id or game.confirmed_by is not None):
        return False
    db.delete(game)
    db.commit()
    return True


def leave_team(db: Session, user_id: uuid.UUID, team_id: uuid.UUID) -> bool:
    """Remove the caller from a team's members.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the session's acting
            user.
        team_id: The team.

    Returns:
        True if a membership was removed, False when the caller was not a member.

    Note:
        Commits.
    """
    if _is_postgres(db):
        done = bool(db.execute(text("SELECT account_leave_team(:t)"), {"t": team_id}).scalar())
        db.commit()
        return done
    gone = db.query(TeamMemberModel).filter(
        TeamMemberModel.team_id == team_id, TeamMemberModel.member_id == user_id,
    ).delete(synchronize_session=False)
    db.commit()
    return gone > 0


# --- Phase 3 items 8-9 (D13): the team board, the directory, requests to join ---

def opted_in(user: UserModel | None) -> bool:
    """Return whether a user has chosen to appear on boards (off unless chosen)."""
    return bool(user is not None and (user.preferences or {}).get("leaderboard_opt_in") is True)


def _people(db: Session, team: TeamModel) -> set[uuid.UUID]:
    """Return everyone on a team: its captain and its members."""
    return {team.user_id} | {m.member_id for m in db.query(TeamMemberModel).filter_by(team_id=team.id)}


@dataclass(frozen=True)
class BoardRow:
    """One player on a team's board.

    Attributes:
        name: Their display name.
        points: Their points in the window.
        is_me: Whether it's the caller.
    """
    name: str
    points: int
    is_me: bool


def team_board(db: Session, user_id: uuid.UUID, team_id: uuid.UUID, start: date, end: date) -> list[BoardRow]:
    """Return a team's board for a window of at most 7 days: opted-in players' points.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the acting user.
        team_id: The team.
        start: First day, inclusive.
        end: Last day, inclusive; at most 6 days after `start`.

    Returns:
        Opted-in players by points, most first; empty unless the caller is on the
        team and opted in too.
    """
    if _is_postgres(db):
        rows = db.execute(text("SELECT * FROM account_team_board(:t, :s, :e)"),
                          {"t": team_id, "s": start, "e": end}).all()
        return [BoardRow(r.name, r.points, r.is_me) for r in rows]
    team = _on_team(db, user_id, team_id)
    if team is None or not opted_in(db.get(UserModel, user_id)) or not 0 <= (end - start).days <= 6:
        return []
    out = []
    for person in _people(db, team):
        user = _live(db, person)
        if user is None or not opted_in(user):
            continue
        total = sum(a.points for a in db.query(ActivityModel).filter(
            ActivityModel.user_id == person, ActivityModel.on_date >= start, ActivityModel.on_date <= end))
        out.append(BoardRow(user.name, total, person == user_id))
    return sorted(out, key=lambda row: (-row.points, row.name))


def listed_teams(db: Session) -> list[TeamModel]:
    """Return the listed teams whose captains' accounts aren't being deleted."""
    return [team for team in db.query(TeamModel).filter(TeamModel.listed.is_(True))
            if _live(db, team.user_id) is not None]


@dataclass(frozen=True)
class DirectoryTeam:
    """A listed team as the directory shows it: never a member's name.

    Attributes:
        team_id: The team, for asking to join.
        name: Its name.
        sport: Its sport, or None.
        level: "casual", "intermediate" or "competitive", or None.
        area: Where it plays, or None.
        looking: Whether it wants players.
        blurb: Its line about itself, or None.
        members: How many are on it, the captain included.
        last_game_on: Its latest recorded game, or None.
        mine: Whether the caller is on it.
        requested: The caller's request to join it ("pending", "accepted",
            "declined"), or None.
    """
    team_id: uuid.UUID
    name: str
    sport: str | None
    level: str | None
    area: str | None
    looking: bool
    blurb: str | None
    members: int
    last_game_on: date | None
    mine: bool
    requested: str | None


def directory(db: Session, user_id: uuid.UUID) -> list[DirectoryTeam]:
    """Return the league directory: listed teams, once `DIRECTORY_FLOOR` are listed.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the acting user.

    Returns:
        The listed teams by name; empty while fewer than the floor are listed.
    """
    if _is_postgres(db):
        rows = db.execute(text("SELECT * FROM account_team_directory()")).all()
        return [DirectoryTeam(*row) for row in rows]
    teams = listed_teams(db)
    if len(teams) < DIRECTORY_FLOOR:
        return []
    out = []
    for team in teams:
        games = [g.played_on for g in db.query(GameModel).filter_by(team_id=team.id)]
        mine = db.query(TeamJoinRequestModel).filter_by(team_id=team.id, user_id=user_id).first()
        out.append(DirectoryTeam(team.id, team.name, team.sport, team.level, team.area, team.looking_for_players,
                                 team.blurb, len(_people(db, team)), max(games) if games else None,
                                 _on_team(db, user_id, team.id) is not None, mine.status if mine else None))
    return sorted(out, key=lambda team: team.name.lower())


def request_to_join(db: Session, user_id: uuid.UUID, team_id: uuid.UUID, message: str | None) -> str:
    """Ask to join a listed team, sending the captain your name and a message.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the acting user.
        team_id: The team.
        message: Up to 200 characters, or None.

    Returns:
        "sent"; "not_listed" while the directory is closed or the team isn't listed;
        "own" for someone already on it; "already" for a second request to it;
        "limit" at `MAX_PENDING_REQUESTS` waiting; "invalid" for an unusable caller or
        message.

    Note:
        Commits.
    """
    if _is_postgres(db):
        status = db.execute(text("SELECT account_request_to_join(:t, :m)"), {"t": team_id, "m": message}).scalar()
        db.commit()
        return status
    if _live(db, user_id) is None or len(message or "") > 200:
        return "invalid"
    teams = listed_teams(db)
    team = next((t for t in teams if t.id == team_id), None)
    if len(teams) < DIRECTORY_FLOOR or team is None:
        return "not_listed"
    if _on_team(db, user_id, team_id) is not None:
        return "own"
    mine = db.query(TeamJoinRequestModel).filter(TeamJoinRequestModel.user_id == user_id)
    if mine.filter(TeamJoinRequestModel.team_id == team_id).first() is not None:
        return "already"
    if mine.filter(TeamJoinRequestModel.status == "pending").count() >= MAX_PENDING_REQUESTS:
        return "limit"
    db.add(TeamJoinRequestModel(user_id=user_id, team_id=team_id, team_name=team.name,
                                message=(message or "").strip() or None, status="pending", created_at=utc_now()))
    db.commit()
    return "sent"


@dataclass(frozen=True)
class JoinRequest:
    """A waiting request to join, as the team's captain sees it: never the requester's id.

    Attributes:
        request_id: The request, for answering it.
        requester_name: Who asked.
        message: What they said, or None.
        created_at: When they asked (naive UTC).
    """
    request_id: uuid.UUID
    requester_name: str
    message: str | None
    created_at: datetime


def team_requests(db: Session, user_id: uuid.UUID, team_id: uuid.UUID) -> list[JoinRequest]:
    """Return a team's waiting requests to join, to its captain alone.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the acting user.
        team_id: The team.

    Returns:
        The waiting requests, oldest first; empty for anyone but the captain.
    """
    if _is_postgres(db):
        rows = db.execute(text("SELECT * FROM account_team_requests(:t)"), {"t": team_id}).all()
        return [JoinRequest(*row) for row in rows]
    team = db.get(TeamModel, team_id)
    if team is None or team.user_id != user_id:
        return []
    out = []
    for request in db.query(TeamJoinRequestModel).filter_by(team_id=team_id, status="pending"):
        requester = _live(db, request.user_id)
        if requester is not None:
            out.append(JoinRequest(request.id, requester.name, request.message, request.created_at))
    return sorted(out, key=lambda r: r.created_at)


def answer_request(db: Session, user_id: uuid.UUID, request_id: uuid.UUID, accept: bool) -> str:
    """Accept or decline a request to join, as the team's captain.

    Args:
        db: Open session acting as the caller.
        user_id: The caller. Read on SQLite only; Postgres uses the acting user.
        request_id: The request.
        accept: True puts the requester on the team.

    Returns:
        "accepted" or "declined"; "full" at `MAX_TEAM_MEMBERS`; "invalid" when it isn't
        a waiting request to the caller's team, or either account is being deleted.

    Note:
        Commits.
    """
    if _is_postgres(db):
        status = db.execute(text("SELECT account_answer_join_request(:r, :a)"),
                            {"r": request_id, "a": accept}).scalar()
        db.commit()
        return status
    request = db.get(TeamJoinRequestModel, request_id)
    team = db.get(TeamModel, request.team_id) if request is not None and request.status == "pending" else None
    if team is None or team.user_id != user_id:
        return "invalid"
    if not accept:
        request.status, request.answered_at = "declined", utc_now()
        db.commit()
        return "declined"
    requester, captain = _live(db, request.user_id), _live(db, user_id)
    if requester is None or captain is None:
        return "invalid"
    if db.query(TeamMemberModel).filter_by(team_id=team.id).count() >= MAX_TEAM_MEMBERS:
        return "full"
    if db.query(TeamMemberModel).filter_by(team_id=team.id, member_id=requester.id).first() is None:
        db.add(TeamMemberModel(id=uuid.uuid4(), team_id=team.id, member_id=requester.id,
                               member_name=requester.name, owner_name=captain.name, joined_at=utc_now()))
    request.status, request.answered_at = "accepted", utc_now()
    db.commit()
    return "accepted"
