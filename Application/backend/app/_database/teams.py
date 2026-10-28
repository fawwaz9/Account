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
    MAX_TEAM_MEMBERS, GameModel, TeamInviteModel, TeamMemberModel, TeamModel, UserModel, utc_now,
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
