"""Teams and games (Phase 2 item 11, D26).

The captain's half reads and writes only the captain's own rows: the team,
its members and its link. Everything about games, for the captain as much as
anyone, goes through ``teams`` -- the definer functions -- so a score counts
only once someone other than its recorder confirms it.
"""
import hashlib
import secrets
import uuid
from datetime import timedelta

from sqlalchemy.orm import Session

from app._database import teams
from app._database.models import INVITE_DAYS, TeamInviteModel, TeamMemberModel, TeamModel, utc_now
from app.Teams.schemas.team import (
    DisputeIn, GameIn, GameOut, Link, Member, NewLink, Record, TeamDetail, TeamIn, TeamInvitePreview, TeamSummary,
    TeamUpdate,
)
from app.shared.dates import user_for


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def record_of(games: list[teams.Game]) -> Record:
    """Wins, losses, ties and points, from confirmed games only."""
    record = Record()
    for game in games:
        if game.confirmed_by_name is None:
            record.unconfirmed += 1
            continue
        record.points_for += game.our_score
        record.points_against += game.their_score
        if game.our_score > game.their_score:
            record.wins += 1
        elif game.our_score < game.their_score:
            record.losses += 1
        else:
            record.ties += 1
    return record


def _own(db: Session, user_id: uuid.UUID, team_id: uuid.UUID) -> TeamModel | None:
    return db.query(TeamModel).filter(TeamModel.id == team_id, TeamModel.user_id == user_id).first()


def _roster(db: Session, team_id: uuid.UUID) -> list[TeamMemberModel]:
    return (db.query(TeamMemberModel).filter(TeamMemberModel.team_id == team_id)
            .order_by(TeamMemberModel.joined_at, TeamMemberModel.member_name).all())


def _live_links(db: Session, team_id: uuid.UUID):
    return db.query(TeamInviteModel).filter(
        TeamInviteModel.team_id == team_id, TeamInviteModel.revoked_at.is_(None),
        TeamInviteModel.expires_at > utc_now(),
    )


def _summaries(db: Session, user_id: uuid.UUID) -> list[TeamSummary]:
    me = user_for(db, user_id)
    out = []
    for team in db.query(TeamModel).filter(TeamModel.user_id == user_id).order_by(TeamModel.name):
        out.append(TeamSummary(team_id=team.id, name=team.name, sport=team.sport, captain_name=me.name,
                               is_captain=True, member_names=[m.member_name for m in _roster(db, team.id)],
                               record=record_of(teams.games(db, user_id, team.id))))
    for team in teams.member_teams(db, user_id):
        out.append(TeamSummary(team_id=team.team_id, name=team.team_name, sport=team.sport,
                               captain_name=team.captain_name, is_captain=False, member_names=team.member_names,
                               record=record_of(teams.games(db, user_id, team.team_id))))
    return out


def overview(db: Session, user_id: uuid.UUID) -> list[TeamSummary] | None:
    if user_for(db, user_id) is None:
        return None
    return _summaries(db, user_id)


def detail(db: Session, user_id: uuid.UUID, team_id: uuid.UUID) -> TeamDetail | None:
    """None when you're not on the team: the same as a team that doesn't exist."""
    summary = next((t for t in _summaries(db, user_id) if t.team_id == team_id), None)
    if summary is None:
        return None
    games = [GameOut(**g.__dict__) for g in teams.games(db, user_id, team_id)]
    members = link = None
    if summary.is_captain:
        members = [Member(id=m.id, name=m.member_name, joined_at=m.joined_at) for m in _roster(db, team_id)]
        live = _live_links(db, team_id).order_by(TeamInviteModel.created_at.desc()).first()
        link = Link(expires_at=live.expires_at) if live else None
    return TeamDetail(**summary.model_dump(), games=games, members=members, link=link)


# ---------------------------------------------------------------- the captain --

def create(db: Session, user_id: uuid.UUID, data: TeamIn) -> TeamDetail | None:
    if user_for(db, user_id) is None:
        return None
    team = TeamModel(id=uuid.uuid4(), user_id=user_id, name=data.name, sport=data.sport, created_at=utc_now())
    db.add(team)
    db.commit()
    return detail(db, user_id, team.id)


def update(db: Session, user_id: uuid.UUID, team_id: uuid.UUID, data: TeamUpdate) -> TeamDetail | None:
    team = _own(db, user_id, team_id)
    if team is None:
        return None
    fields = data.model_dump(exclude_unset=True)
    if fields.get("name") is not None:
        team.name = fields["name"]
    if "sport" in fields:
        team.sport = (fields["sport"] or "").strip() or None
    db.commit()
    return detail(db, user_id, team_id)


def delete(db: Session, user_id: uuid.UUID, team_id: uuid.UUID) -> str | None:
    """The team's name when it is gone; games, members and link go with it."""
    team = _own(db, user_id, team_id)
    if team is None:
        return None
    name = team.name
    db.delete(team)
    db.commit()
    return name


def new_link(db: Session, user_id: uuid.UUID, team_id: uuid.UUID) -> NewLink | None:
    team = _own(db, user_id, team_id)
    if team is None:
        return None
    now = utc_now()
    for old in _live_links(db, team.id):
        old.revoked_at = now
    token = secrets.token_urlsafe(24)
    link = TeamInviteModel(id=uuid.uuid4(), team_id=team.id, token_hash=token_hash(token), created_at=now,
                           expires_at=now + timedelta(days=INVITE_DAYS))
    db.add(link)
    db.commit()
    return NewLink(token=token, expires_at=link.expires_at)


def cancel_link(db: Session, user_id: uuid.UUID, team_id: uuid.UUID) -> bool:
    team = _own(db, user_id, team_id)
    if team is None:
        return False
    now = utc_now()
    for old in _live_links(db, team.id):
        old.revoked_at = now
    db.commit()
    return True


def remove_member(db: Session, user_id: uuid.UUID, team_id: uuid.UUID, member_id: uuid.UUID) -> bool:
    team = _own(db, user_id, team_id)
    if team is None:
        return False
    member = db.query(TeamMemberModel).filter(TeamMemberModel.id == member_id,
                                              TeamMemberModel.team_id == team.id).first()
    if member is None:
        return False
    db.delete(member)
    db.commit()
    return True


# ------------------------------------------------------------ anyone on it --

def _game_of(db: Session, user_id: uuid.UUID, team_id: uuid.UUID, game_id: uuid.UUID) -> bool:
    """The game is this team's, and you're on the team."""
    return any(g.game_id == game_id for g in teams.games(db, user_id, team_id))


def record_game(db: Session, user_id: uuid.UUID, team_id: uuid.UUID, data: GameIn) -> TeamDetail | None:
    made = teams.record_game(db, user_id, team_id, data.played_on, data.opponent, data.our_score, data.their_score)
    return detail(db, user_id, team_id) if made else None


def confirm_game(db: Session, user_id: uuid.UUID, team_id: uuid.UUID, game_id: uuid.UUID) -> bool | None:
    """None when there is no such game for you; False when it can't be confirmed."""
    if not _game_of(db, user_id, team_id, game_id):
        return None
    return teams.confirm_game(db, user_id, game_id)


def dispute_game(db: Session, user_id: uuid.UUID, team_id: uuid.UUID, game_id: uuid.UUID,
                 data: DisputeIn) -> bool | None:
    if not _game_of(db, user_id, team_id, game_id):
        return None
    return teams.dispute_game(db, user_id, game_id, data.our_score, data.their_score)


def correct_game(db: Session, user_id: uuid.UUID, team_id: uuid.UUID, game_id: uuid.UUID,
                 data: GameIn) -> bool | None:
    if not _game_of(db, user_id, team_id, game_id):
        return None
    return teams.correct_game(db, user_id, game_id, data.played_on, data.opponent, data.our_score,
                              data.their_score)


def delete_game(db: Session, user_id: uuid.UUID, team_id: uuid.UUID, game_id: uuid.UUID) -> bool | None:
    if not _game_of(db, user_id, team_id, game_id):
        return None
    return teams.delete_game(db, user_id, game_id)


def leave(db: Session, user_id: uuid.UUID, team_id: uuid.UUID) -> bool:
    return teams.leave_team(db, user_id, team_id)


def preview(db: Session, user_id: uuid.UUID, token: str) -> TeamInvitePreview | None:
    found = teams.invite_preview(db, user_id, token_hash(token))
    return TeamInvitePreview(**found.__dict__) if found else None


def accept(db: Session, user_id: uuid.UUID, token: str) -> str:
    return teams.accept_invite(db, user_id, token_hash(token))
