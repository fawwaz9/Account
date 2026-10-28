"""Fitness routes under `/api/fitness` beyond teams (Phase 3 items 6-9 and 13).

Every route reads and writes the caller's own rows; what the caller sees of anyone
else comes through a definer function, and only among their own connections.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app._database import teams
from app.Fitness.schemas.fitness import (
    Activity, ActivityIn, CampusBoard, Directory, Exertion, GoalIn, GymBuddies, GymBuddyIn, JoinAnswer, JoinIn,
    MyJoinRequest, Status, TeamBoard, TeamJoinRequestOut,
)
from app.Fitness.services import exertion_service, gym_buddy_service, league_service
from app.shared.errors import error_user, responses

router = APIRouter()


@router.get("/{user_id}/gym-buddy", response_model=GymBuddies)
def get_gym_buddy(user_id: VerifiedUserId, db: DBSession):
    """Read the caller's gym-buddy status and the connections looking too.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The status, and partners and teammates also looking, while the caller is.
    """
    return gym_buddy_service.read(db, user_id)


@router.put("/{user_id}/gym-buddy", response_model=GymBuddies)
def save_gym_buddy(user_id: VerifiedUserId, body: GymBuddyIn, db: DBSession):
    """Say whether the caller is looking for someone to train with.

    Args:
        user_id: The verified caller's id.
        body: Looking or not, when, and a note.
        db: Request-scoped database session.

    Returns:
        The saved status and the connections looking too.
    """
    return gym_buddy_service.save(db, user_id, body)


@router.get("/{user_id}/exertion", response_model=Exertion, responses=responses["user_404"])
def get_exertion(user_id: VerifiedUserId, db: DBSession):
    """Read this week's exertion points against the goal, the weeks before, and a suggestion.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The week, the goal, a suggested goal with its reason, 8 weeks before, and the
        last 28 days' activities.

    Raises:
        HTTPException: 404 when the user does not exist.
    """
    found = exertion_service.summary(db, user_id)
    if found is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return found


@router.put("/{user_id}/exertion/goal", response_model=Exertion, responses=responses["user_404"])
def set_goal(user_id: VerifiedUserId, body: GoalIn, db: DBSession):
    """Set the weekly exertion goal, or clear it with null.

    Args:
        user_id: The verified caller's id.
        body: The goal.
        db: Request-scoped database session.

    Returns:
        The summary with the new goal.

    Raises:
        HTTPException: 404 when the user does not exist.
    """
    found = exertion_service.set_goal(db, user_id, body.goal)
    if found is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return found


@router.post("/{user_id}/activities", response_model=Activity)
def log_activity(user_id: VerifiedUserId, body: ActivityIn, db: DBSession):
    """Log an activity; its points are worked out now and never rewritten.

    Args:
        user_id: The verified caller's id.
        body: What, when and how long.
        db: Request-scoped database session.

    Returns:
        The activity with its points.
    """
    return exertion_service.log(db, user_id, body)


@router.delete("/{user_id}/activities/{activity_id}", responses={404: {"description": "Activity not found"}})
def delete_activity(user_id: VerifiedUserId, activity_id: UUID, db: DBSession):
    """Delete one of the caller's activities.

    Args:
        user_id: The verified caller's id.
        activity_id: The activity.
        db: Request-scoped database session.

    Returns:
        `{"deleted": true}`.

    Raises:
        HTTPException: 404 when it is missing or another user's.
    """
    if not exertion_service.delete(db, user_id, activity_id):
        raise HTTPException(status_code=404, detail="Activity not found")
    return {"deleted": True}


@router.get("/{user_id}/teams/{team_id}/board", response_model=TeamBoard)
def get_team_board(user_id: VerifiedUserId, team_id: UUID, db: DBSession):
    """Read a team's board this week: teammates who opted in, if the caller has too.

    Args:
        user_id: The verified caller's id.
        team_id: The team.
        db: Request-scoped database session.

    Returns:
        Whether the caller is opted in, the week, and opted-in teammates' points;
        empty for a team the caller isn't on.
    """
    return league_service.team_board(db, user_id, team_id)


@router.get("/{user_id}/campus-board", response_model=CampusBoard)
def get_campus_board(user_id: VerifiedUserId, db: DBSession):
    """Read this week's campus board: listed teams by points, never a person.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The board; empty until 5 teams are listed.
    """
    return league_service.campus_board(db)


@router.get("/{user_id}/directory", response_model=Directory)
def get_directory(user_id: VerifiedUserId, db: DBSession):
    """Read the league directory: listed teams, never a member's name.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The directory; empty until 5 teams are listed.
    """
    return league_service.directory(db, user_id)


@router.post("/{user_id}/directory/{team_id}/join", response_model=Status)
def join_team(user_id: VerifiedUserId, team_id: UUID, body: JoinIn, db: DBSession):
    """Ask to join a listed team; the captain sees your name and message.

    Args:
        user_id: The verified caller's id.
        team_id: The team.
        body: A message for the captain.
        db: Request-scoped database session.

    Returns:
        "sent", or why not: "not_listed", "own", "already", "limit" or "invalid".
    """
    return Status(status=teams.request_to_join(db, user_id, team_id, body.message))


@router.get("/{user_id}/join-requests", response_model=list[MyJoinRequest])
def list_my_requests(user_id: VerifiedUserId, db: DBSession):
    """List the caller's own requests to join teams and where each stands.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The requests, newest first.
    """
    return league_service.my_requests(db, user_id)


@router.delete("/{user_id}/join-requests/{request_id}", responses={404: {"description": "Request not found"}})
def withdraw_request(user_id: VerifiedUserId, request_id: UUID, db: DBSession):
    """Take back one of the caller's waiting requests to join.

    Args:
        user_id: The verified caller's id.
        request_id: The request.
        db: Request-scoped database session.

    Returns:
        `{"deleted": true}`.

    Raises:
        HTTPException: 404 when it isn't the caller's, or has been answered.
    """
    if not league_service.withdraw(db, user_id, request_id):
        raise HTTPException(status_code=404, detail="No waiting request to take back")
    return {"deleted": True}


@router.get("/{user_id}/teams/{team_id}/join-requests", response_model=list[TeamJoinRequestOut])
def list_team_requests(user_id: VerifiedUserId, team_id: UUID, db: DBSession):
    """List the waiting requests to join a team the caller captains.

    Args:
        user_id: The verified caller's id.
        team_id: The team.
        db: Request-scoped database session.

    Returns:
        The requests, oldest first; empty for anyone but its captain.
    """
    return league_service.team_requests(db, user_id, team_id)


@router.post("/{user_id}/join-requests/{request_id}/answer", response_model=Status)
def answer_request(user_id: VerifiedUserId, request_id: UUID, body: JoinAnswer, db: DBSession):
    """Accept or decline a request to join the caller's team.

    Args:
        user_id: The verified caller's id.
        request_id: The request.
        body: Whether to accept.
        db: Request-scoped database session.

    Returns:
        "accepted", "declined", "full", or "invalid" for anything but a waiting
        request to the caller's team.
    """
    return Status(status=teams.answer_request(db, user_id, request_id, body.accept))
