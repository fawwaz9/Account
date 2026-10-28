"""Teams and games on the Fitness page: the captain's management and everyone's games.

The captain reads and writes their own rows (the team, its members, its link).
Every game read and write, the captain's included, goes through the definer
functions in `_database/teams.py`, so a score counts only once someone other than
its recorder confirms it.
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
    """Return the SHA-256 hex digest of a link token, which is all that is stored.

    Args:
        token: The raw token from the team link.

    Returns:
        The 64-character hex digest.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def record_of(games: list[teams.Game]) -> Record:
    """Return a team's wins, losses, ties and points from its confirmed games.

    Unconfirmed and disputed games are only counted as `unconfirmed`.

    Args:
        games: The team's games, as a member sees them.

    Returns:
        The record; `unconfirmed` counts the games left out of it.
    """
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
    """Return the team if the caller is its captain, else None."""
    return db.query(TeamModel).filter(TeamModel.id == team_id, TeamModel.user_id == user_id).first()


def _roster(db: Session, team_id: uuid.UUID) -> list[TeamMemberModel]:
    """Return a team's members in joining order."""
    return (db.query(TeamMemberModel).filter(TeamMemberModel.team_id == team_id)
            .order_by(TeamMemberModel.joined_at, TeamMemberModel.member_name).all())


def _live_links(db: Session, team_id: uuid.UUID):
    """Return a query for the team's unrevoked, unexpired join links."""
    return db.query(TeamInviteModel).filter(
        TeamInviteModel.team_id == team_id, TeamInviteModel.revoked_at.is_(None),
        TeamInviteModel.expires_at > utc_now(),
    )


def _summaries(db: Session, user_id: uuid.UUID) -> list[TeamSummary]:
    """Return every team the caller captains (by name), then those they play on."""
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
    """Return every team the caller captains or plays on, with records.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.

    Returns:
        The summaries, or None when the user does not exist.
    """
    if user_for(db, user_id) is None:
        return None
    return _summaries(db, user_id)


def detail(db: Session, user_id: uuid.UUID, team_id: uuid.UUID) -> TeamDetail | None:
    """Return one team with its games, plus the roster and live link for the captain.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        team_id: The team.

    Returns:
        The team, or None when the caller is not on it, the same answer as for a team
        that does not exist.
    """
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
    """Create a team with the caller as captain.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        data: Name and sport.

    Returns:
        The new team's detail, or None when the user does not exist.

    Note:
        Commits.
    """
    if user_for(db, user_id) is None:
        return None
    team = TeamModel(id=uuid.uuid4(), user_id=user_id, name=data.name, sport=data.sport, created_at=utc_now())
    db.add(team)
    db.commit()
    return detail(db, user_id, team.id)


def update(db: Session, user_id: uuid.UUID, team_id: uuid.UUID, data: TeamUpdate) -> TeamDetail | None:
    """Rename a team or change its sport; captain only.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        team_id: The team.
        data: The fields to change; a blank sport is stored as None.

    Returns:
        The team's detail, or None when the caller is not its captain.

    Note:
        Commits.
    """
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
    """Delete a team with its games, members and links; captain only.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        team_id: The team.

    Returns:
        The deleted team's name, or None when the caller is not its captain.

    Note:
        Commits.
    """
    team = _own(db, user_id, team_id)
    if team is None:
        return None
    name = team.name
    db.delete(team)
    db.commit()
    return name


def new_link(db: Session, user_id: uuid.UUID, team_id: uuid.UUID) -> NewLink | None:
    """Make a new join link for a team, revoking any live one; captain only.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        team_id: The team.

    Returns:
        The link's token, shown this once, and its expiry; None when the caller is not
        the captain.

    Note:
        Commits; only the token's hash is stored.
    """
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
    """Revoke a team's live join links; captain only.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        team_id: The team.

    Returns:
        True when the caller is the captain (whether or not a link was live).

    Note:
        Commits.
    """
    team = _own(db, user_id, team_id)
    if team is None:
        return False
    now = utc_now()
    for old in _live_links(db, team.id):
        old.revoked_at = now
    db.commit()
    return True


def remove_member(db: Session, user_id: uuid.UUID, team_id: uuid.UUID, member_id: uuid.UUID) -> bool:
    """Take a member off a team; captain only.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        team_id: The team.
        member_id: The membership row's id.

    Returns:
        True if removed; False when the caller is not the captain or there is no such
        member.

    Note:
        Commits.
    """
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
    """Return whether the game is this team's and the caller is on the team."""
    return any(g.game_id == game_id for g in teams.games(db, user_id, team_id))


def record_game(db: Session, user_id: uuid.UUID, team_id: uuid.UUID, data: GameIn) -> TeamDetail | None:
    """Record a game for a team the caller is on.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        team_id: The team.
        data: Date, opponent and scores.

    Returns:
        The team's detail, or None when the caller is not on the team or the game was
        refused.
    """
    made = teams.record_game(db, user_id, team_id, data.played_on, data.opponent, data.our_score, data.their_score)
    return detail(db, user_id, team_id) if made else None


def confirm_game(db: Session, user_id: uuid.UUID, team_id: uuid.UUID, game_id: uuid.UUID) -> bool | None:
    """Confirm another player's game.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        team_id: The team.
        game_id: The game.

    Returns:
        None when the caller has no such game; otherwise whether it was confirmed.
    """
    if not _game_of(db, user_id, team_id, game_id):
        return None
    return teams.confirm_game(db, user_id, game_id)


def dispute_game(db: Session, user_id: uuid.UUID, team_id: uuid.UUID, game_id: uuid.UUID,
                 data: DisputeIn) -> bool | None:
    """Dispute another player's unconfirmed game with the scores the caller believes.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        team_id: The team.
        game_id: The game.
        data: The disputed scores.

    Returns:
        None when the caller has no such game; otherwise whether the dispute was stored.
    """
    if not _game_of(db, user_id, team_id, game_id):
        return None
    return teams.dispute_game(db, user_id, game_id, data.our_score, data.their_score)


def correct_game(db: Session, user_id: uuid.UUID, team_id: uuid.UUID, game_id: uuid.UUID,
                 data: GameIn) -> bool | None:
    """Correct the caller's own unconfirmed game, clearing any dispute.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        team_id: The team.
        game_id: The game.
        data: The corrected date, opponent and scores.

    Returns:
        None when the caller has no such game; otherwise whether it was corrected.
    """
    if not _game_of(db, user_id, team_id, game_id):
        return None
    return teams.correct_game(db, user_id, game_id, data.played_on, data.opponent, data.our_score,
                              data.their_score)


def delete_game(db: Session, user_id: uuid.UUID, team_id: uuid.UUID, game_id: uuid.UUID) -> bool | None:
    """Delete a game: the recorder while unconfirmed, or the captain at any time.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        team_id: The team.
        game_id: The game.

    Returns:
        None when the caller has no such game; otherwise whether it was deleted.
    """
    if not _game_of(db, user_id, team_id, game_id):
        return None
    return teams.delete_game(db, user_id, game_id)


def leave(db: Session, user_id: uuid.UUID, team_id: uuid.UUID) -> bool:
    """Leave a team the caller plays on; returns whether a membership was removed.

    Args:
        db: Open session acting as the caller.
        user_id: The caller.
        team_id: The team to leave.

    Returns:
        True when the caller was a member and is no longer.
    """
    return teams.leave_team(db, user_id, team_id)


def preview(db: Session, user_id: uuid.UUID, token: str) -> TeamInvitePreview | None:
    """Return what a team link shows, or None when it is not live.

    Args:
        db: Open session acting as the caller.
        user_id: The caller.
        token: The raw token from the link.

    Returns:
        The team's name, sport and size, or None when the link is unknown or expired.
    """
    found = teams.invite_preview(db, user_id, token_hash(token))
    return TeamInvitePreview(**found.__dict__) if found else None


def accept(db: Session, user_id: uuid.UUID, token: str) -> str:
    """Join a team through its link; returns the definer function's status word.

    Args:
        db: Open session acting as the caller.
        user_id: The caller.
        token: The raw token from the link.

    Returns:
        The status word, such as "accepted" or "invalid".
    """
    return teams.accept_invite(db, user_id, token_hash(token))
