"""The cross-user steps of teams (Phase 2 item 11, D26).

Like ``sharing.py``: on Postgres each is a ``SECURITY DEFINER`` function in
``rls.FUNCTION_SQL``, keyed on the session's identity; on SQLite, which has no
row security, the same rule is a plain query written to mean exactly what the
function means. The tests run both.

"On the team" means the captain or a member, of a captain whose account is
not being deleted. Every game write comes through here, the captain's
included.
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
    return db.get_bind().dialect.name == "postgresql"


@dataclass(frozen=True)
class TeamInvitePreview:
    captain_name: str
    team_name: str
    sport: str | None


@dataclass(frozen=True)
class MemberTeam:
    team_id: uuid.UUID
    team_name: str
    sport: str | None
    captain_name: str
    member_names: list[str]


@dataclass(frozen=True)
class Game:
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
    user = db.get(UserModel, user_id)
    return user if user is not None and user.deleted_at is None else None


def _on_team(db: Session, user_id: uuid.UUID, team_id: uuid.UUID) -> TeamModel | None:
    team = db.get(TeamModel, team_id)
    if team is None or _live(db, team.user_id) is None:
        return None
    if team.user_id == user_id:
        return team
    member = db.query(TeamMemberModel).filter_by(team_id=team_id, member_id=user_id).first()
    return team if member is not None else None


def _scores_ok(*scores) -> bool:
    return all(s is not None and 0 <= s <= 999 for s in scores)


def _opponent_ok(opponent: str | None) -> bool:
    return 1 <= len((opponent or "").strip()) <= 60


def _live_invite(db: Session, token_hash: str):
    return (
        db.query(TeamInviteModel)
        .filter(TeamInviteModel.token_hash == token_hash, TeamInviteModel.revoked_at.is_(None),
                TeamInviteModel.expires_at > utc_now())
        .first()
    )


def invite_preview(db: Session, user_id: uuid.UUID, token_hash: str) -> TeamInvitePreview | None:
    if _is_postgres(db):
        row = db.execute(text("SELECT * FROM account_team_invite_preview(:h)"), {"h": token_hash}).first()
        return TeamInvitePreview(row.captain_name, row.team_name, row.sport) if row else None
    invite = _live_invite(db, token_hash)
    team = db.get(TeamModel, invite.team_id) if invite else None
    captain = _live(db, team.user_id) if team else None
    return TeamInvitePreview(captain.name, team.name, team.sport) if captain else None


def accept_invite(db: Session, user_id: uuid.UUID, token_hash: str) -> str:
    """'accepted', 'invalid', 'own', 'already' or 'full'."""
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
    """Teams the caller plays on as a member; a captain reads their own."""
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
    game = db.get(GameModel, game_id)
    if game is None or _on_team(db, user_id, game.team_id) is None:
        return None
    return game


def _clear_dispute(game: GameModel) -> None:
    game.disputed_by = game.disputed_by_name = game.disputed_our = game.disputed_their = None


def confirm_game(db: Session, user_id: uuid.UUID, game_id: uuid.UUID) -> bool:
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
    if _is_postgres(db):
        done = bool(db.execute(text("SELECT account_leave_team(:t)"), {"t": team_id}).scalar())
        db.commit()
        return done
    gone = db.query(TeamMemberModel).filter(
        TeamMemberModel.team_id == team_id, TeamMemberModel.member_id == user_id,
    ).delete(synchronize_session=False)
    db.commit()
    return gone > 0
