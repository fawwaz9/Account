"""Boards and the league directory (Phase 3 items 8 and 9, D13).

A team's board shows teammates who opted in, to teammates who opted in. The campus
board ranks listed teams, never people, once 5 are listed; the directory opens at the
same point. Asking to join sends the captain your name and a message; they answer.
Every cross-user read or write is a definer function in `_database`.
"""
import uuid
from datetime import timedelta

from sqlalchemy.orm import Session

from app._database import aggregates, teams
from app._database.models import DIRECTORY_FLOOR, TeamJoinRequestModel, UserModel
from app.Fitness.schemas.fitness import (
    BoardRowOut, CampusBoard, CampusTeam, Directory, DirectoryTeamOut, MyJoinRequest, TeamBoard, TeamJoinRequestOut,
)
from app.Fitness.services.exertion_service import monday_of
from app.shared.dates import user_today

#: A team with no game in this many days is shown greyed in the directory.
DORMANT_DAYS = 30


def team_board(db: Session, user_id: uuid.UUID, team_id: uuid.UUID) -> TeamBoard:
    """Return a team's board for the caller's current week.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        team_id: The team.

    Returns:
        Opted-in teammates' points this week; empty for someone not on the team or
        not opted in.
    """
    week = monday_of(user_today(db, user_id))
    rows = teams.team_board(db, user_id, team_id, week, week + timedelta(days=6))
    return TeamBoard(opted_in=teams.opted_in(db.get(UserModel, user_id)), week_start=week,
                     rows=[BoardRowOut(name=r.name, points=r.points, is_me=r.is_me) for r in rows])


def campus_board(db: Session) -> CampusBoard:
    """Return this week's campus board, empty until `DIRECTORY_FLOOR` teams are listed.

    Args:
        db: Request-scoped database session, acting as the caller.

    Returns:
        Listed teams by points.
    """
    rows = aggregates.campus_board(db)
    return CampusBoard(floor=DIRECTORY_FLOOR, week_start=rows[0].week_start if rows else None,
                       teams=[CampusTeam(team_name=r.team_name, sport=r.sport, points=r.points) for r in rows])


def directory(db: Session, user_id: uuid.UUID) -> Directory:
    """Return the league directory, empty until `DIRECTORY_FLOOR` teams are listed.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.

    Returns:
        Listed teams by name, greyed when no game was recorded in 30 days.
    """
    cutoff = user_today(db, user_id) - timedelta(days=DORMANT_DAYS)
    return Directory(floor=DIRECTORY_FLOOR, teams=[
        DirectoryTeamOut(team_id=t.team_id, name=t.name, sport=t.sport, level=t.level, area=t.area,
                         looking=t.looking, blurb=t.blurb, members=t.members, last_game_on=t.last_game_on,
                         dormant=t.last_game_on is None or t.last_game_on < cutoff, mine=t.mine,
                         requested=t.requested)
        for t in teams.directory(db, user_id)
    ])


def my_requests(db: Session, user_id: uuid.UUID) -> list[MyJoinRequest]:
    """Return the caller's own requests to join teams, newest first.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.

    Returns:
        The requests with where each stands.
    """
    rows = (db.query(TeamJoinRequestModel).filter(TeamJoinRequestModel.user_id == user_id)
            .order_by(TeamJoinRequestModel.created_at.desc()).all())
    return [MyJoinRequest.model_validate(row) for row in rows]


def withdraw(db: Session, user_id: uuid.UUID, request_id: uuid.UUID) -> bool:
    """Take back one of the caller's waiting requests to join.

    An answered request stays, so a declined one can't be sent again.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        request_id: The request.

    Returns:
        True if it was deleted; False when it isn't the caller's waiting request.

    Note:
        Commits.
    """
    row = db.query(TeamJoinRequestModel).filter(
        TeamJoinRequestModel.id == request_id, TeamJoinRequestModel.user_id == user_id,
        TeamJoinRequestModel.status == "pending").first()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def team_requests(db: Session, user_id: uuid.UUID, team_id: uuid.UUID) -> list[TeamJoinRequestOut]:
    """Return a team's waiting requests to join, to its captain.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        team_id: The team.

    Returns:
        Requests oldest first; empty for anyone but the captain.
    """
    return [TeamJoinRequestOut(request_id=r.request_id, requester_name=r.requester_name, message=r.message,
                               created_at=r.created_at) for r in teams.team_requests(db, user_id, team_id)]
