"""Team routes under `/api/teams`, the Fitness page: teams, links, members and games.

A team the caller is not on answers 404, the same as one that does not exist. Game
actions refused by the rules answer 409.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Tasks.schemas.sharing import TaskInviteAccepted as InviteAccepted, TaskInviteToken as InviteToken
from app.Teams.schemas.team import (
    DisputeIn, GameIn, NewLink, TeamDetail, TeamIn, TeamInvitePreview, TeamSummary, TeamUpdate,
)
from app.Teams.services import team_service as service
from app.shared import audit
from app.shared.errors import error_user, responses

router = APIRouter()

TEAM_404 = {404: {"description": "Team not found"}}
GAME_BOTH = {404: {"description": "Game not found"}, 409: {"description": "Not allowed for this game"}}
"""OpenAPI responses for game actions: 404 for no such game, 409 for a refused one."""
NO_TEAM = "Team not found"
NO_GAME = "Game not found"
NO_LINK = "That link has expired or been cancelled."


@router.get("/{user_id}", response_model=list[TeamSummary], responses=responses["user_404"])
def get_teams(user_id: VerifiedUserId, db: DBSession):
    """List the teams the caller captains or plays on, with their records.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The teams.

    Raises:
        HTTPException: 404 when the user does not exist.
    """
    found = service.overview(db, user_id)
    if found is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return found


@router.post("/{user_id}", response_model=TeamDetail, responses=responses["user_404"])
def create_team(user_id: VerifiedUserId, body: TeamIn, db: DBSession):
    """Create a team with the caller as captain.

    Args:
        user_id: The verified caller's id.
        body: Name and sport.
        db: Request-scoped database session.

    Returns:
        The new team.

    Raises:
        HTTPException: 404 when the user does not exist.
    """
    made = service.create(db, user_id, body)
    if made is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return made


@router.post("/{user_id}/invites/preview", response_model=TeamInvitePreview, responses=responses["user_404"])
def preview_link(user_id: VerifiedUserId, body: InviteToken, db: DBSession):
    """Return whose team a link joins, before accepting it.

    A POST, so the token stays out of URLs and logs.

    Args:
        user_id: The verified caller's id.
        body: The token from the link.
        db: Request-scoped database session.

    Returns:
        The captain's name, team name and sport.

    Raises:
        HTTPException: 404 when the link is unknown, revoked or expired.
    """
    found = service.preview(db, user_id, body.token)
    if found is None:
        raise HTTPException(status_code=404, detail=NO_LINK)
    return found


@router.post("/{user_id}/invites/accept", response_model=InviteAccepted, responses=responses["user_404"])
def accept_link(user_id: VerifiedUserId, body: InviteToken, db: DBSession):
    """Join a team through its link.

    Args:
        user_id: The verified caller's id.
        body: The token from the link.
        db: Request-scoped database session.

    Returns:
        `status`: "accepted", "invalid", "own", "already" or "full".
    """
    return InviteAccepted(status=service.accept(db, user_id, body.token))


@router.get("/{user_id}/{team_id}", response_model=TeamDetail, responses=TEAM_404)
def get_team(user_id: VerifiedUserId, team_id: UUID, db: DBSession):
    """Return a team with its games, and the roster and link for the captain.

    Args:
        user_id: The verified caller's id.
        team_id: The team.
        db: Request-scoped database session.

    Returns:
        The team.

    Raises:
        HTTPException: 404 when the caller is not on the team, as for a team that does
            not exist.
    """
    found = service.detail(db, user_id, team_id)
    if found is None:
        raise HTTPException(status_code=404, detail=NO_TEAM)
    return found


# ---------------------------------------------------------------- the captain --

@router.patch("/{user_id}/{team_id}", response_model=TeamDetail, responses=TEAM_404)
def update_team(user_id: VerifiedUserId, team_id: UUID, body: TeamUpdate, db: DBSession):
    """Rename a team or change its sport; captain only.

    Args:
        user_id: The verified caller's id.
        team_id: The team.
        body: The fields to change.
        db: Request-scoped database session.

    Returns:
        The updated team.

    Raises:
        HTTPException: 404 when the caller is not the team's captain.
    """
    found = service.update(db, user_id, team_id, body)
    if found is None:
        raise HTTPException(status_code=404, detail=NO_TEAM)
    return found


@router.delete("/{user_id}/{team_id}", responses=TEAM_404)
def delete_team(user_id: VerifiedUserId, team_id: UUID, db: DBSession):
    """Delete a team with its games, members and links; captain only, audit-logged.

    Args:
        user_id: The verified caller's id.
        team_id: The team.
        db: Request-scoped database session.

    Returns:
        `{"deleted": true}`.

    Raises:
        HTTPException: 404 when the caller is not the team's captain.
    """
    name = service.delete(db, user_id, team_id)
    if name is None:
        raise HTTPException(status_code=404, detail=NO_TEAM)
    audit.deletion("team", user_id=user_id, target_id=team_id, detail=name)
    return {"deleted": True}


@router.post("/{user_id}/{team_id}/link", response_model=NewLink, responses=TEAM_404)
def make_link(user_id: VerifiedUserId, team_id: UUID, db: DBSession):
    """Make a new join link, cancelling any live one; captain only.

    Args:
        user_id: The verified caller's id.
        team_id: The team.
        db: Request-scoped database session.

    Returns:
        The token, shown this once, and its expiry.

    Raises:
        HTTPException: 404 when the caller is not the team's captain.
    """
    link = service.new_link(db, user_id, team_id)
    if link is None:
        raise HTTPException(status_code=404, detail=NO_TEAM)
    return link


@router.delete("/{user_id}/{team_id}/link", responses=TEAM_404)
def cancel_link(user_id: VerifiedUserId, team_id: UUID, db: DBSession):
    """Cancel the team's live join link; captain only.

    Args:
        user_id: The verified caller's id.
        team_id: The team.
        db: Request-scoped database session.

    Returns:
        `{"cancelled": true}`.

    Raises:
        HTTPException: 404 when the caller is not the team's captain.
    """
    if not service.cancel_link(db, user_id, team_id):
        raise HTTPException(status_code=404, detail=NO_TEAM)
    return {"cancelled": True}


@router.delete("/{user_id}/{team_id}/members/{member_id}", responses=TEAM_404)
def remove_member(user_id: VerifiedUserId, team_id: UUID, member_id: UUID, db: DBSession):
    """Take a member off the team; captain only, audit-logged.

    Args:
        user_id: The verified caller's id.
        team_id: The team.
        member_id: The membership's id.
        db: Request-scoped database session.

    Returns:
        `{"removed": true}`.

    Raises:
        HTTPException: 404 when the caller is not the captain or there is no such
            member.
    """
    if not service.remove_member(db, user_id, team_id, member_id):
        raise HTTPException(status_code=404, detail="Nobody by that id is on this team")
    audit.deletion("team_member", user_id=user_id, target_id=member_id, detail=str(team_id))
    return {"removed": True}


# ------------------------------------------------------------ anyone on it --

@router.delete("/{user_id}/{team_id}/membership", responses=TEAM_404)
def leave_team(user_id: VerifiedUserId, team_id: UUID, db: DBSession):
    """Leave a team the caller plays on.

    Args:
        user_id: The verified caller's id.
        team_id: The team.
        db: Request-scoped database session.

    Returns:
        `{"left": true}`.

    Raises:
        HTTPException: 404 when the caller is not a member.
    """
    if not service.leave(db, user_id, team_id):
        raise HTTPException(status_code=404, detail=NO_TEAM)
    return {"left": True}


@router.post("/{user_id}/{team_id}/games", response_model=TeamDetail, responses=TEAM_404)
def record_game(user_id: VerifiedUserId, team_id: UUID, body: GameIn, db: DBSession):
    """Record a game; it counts once someone other than the recorder confirms it.

    Args:
        user_id: The verified caller's id.
        team_id: The team.
        body: Date, opponent and scores.
        db: Request-scoped database session.

    Returns:
        The team with the new game.

    Raises:
        HTTPException: 404 when the caller is not on the team or the game is refused.
    """
    found = service.record_game(db, user_id, team_id, body)
    if found is None:
        raise HTTPException(status_code=404, detail=NO_TEAM)
    return found


def _game_answer(result: bool | None, refused: str):
    """Map a game action's result to `{"ok": True}`, a 404 or a 409."""
    if result is None:
        raise HTTPException(status_code=404, detail=NO_GAME)
    if result is False:
        raise HTTPException(status_code=409, detail=refused)
    return {"ok": True}


@router.put("/{user_id}/{team_id}/games/{game_id}", responses=GAME_BOTH)
def correct_game(user_id: VerifiedUserId, team_id: UUID, game_id: UUID, body: GameIn, db: DBSession):
    """Correct a game the caller recorded, before it is confirmed; clears any dispute.

    Args:
        user_id: The verified caller's id.
        team_id: The team.
        game_id: The game.
        body: The corrected date, opponent and scores.
        db: Request-scoped database session.

    Returns:
        `{"ok": true}`.

    Raises:
        HTTPException: 404 when the caller has no such game; 409 when they did not
            record it or it is confirmed.
    """
    return _game_answer(service.correct_game(db, user_id, team_id, game_id, body),
                        "Only whoever recorded a game can correct it, and only before it's confirmed.")


@router.post("/{user_id}/{team_id}/games/{game_id}/confirm", responses=GAME_BOTH)
def confirm_game(user_id: VerifiedUserId, team_id: UUID, game_id: UUID, db: DBSession):
    """Confirm someone else's game; confirming over your own dispute withdraws it.

    Args:
        user_id: The verified caller's id.
        team_id: The team.
        game_id: The game.
        db: Request-scoped database session.

    Returns:
        `{"ok": true}`.

    Raises:
        HTTPException: 404 when the caller has no such game; 409 for the recorder, a
            confirmed game, or one disputed by someone else.
    """
    return _game_answer(service.confirm_game(db, user_id, team_id, game_id),
                        "Someone other than whoever recorded it confirms a game, once, and not while it's disputed.")


@router.post("/{user_id}/{team_id}/games/{game_id}/dispute", responses=GAME_BOTH)
def dispute_game(user_id: VerifiedUserId, team_id: UUID, game_id: UUID, body: DisputeIn, db: DBSession):
    """Dispute someone else's unconfirmed game with the scores the caller believes.

    Args:
        user_id: The verified caller's id.
        team_id: The team.
        game_id: The game.
        body: The disputed scores.
        db: Request-scoped database session.

    Returns:
        `{"ok": true}`.

    Raises:
        HTTPException: 404 when the caller has no such game; 409 for the recorder or a
            confirmed game.
    """
    return _game_answer(service.dispute_game(db, user_id, team_id, game_id, body),
                        "Someone other than whoever recorded it can dispute a game, before it's confirmed.")


@router.delete("/{user_id}/{team_id}/games/{game_id}", responses=GAME_BOTH)
def delete_game(user_id: VerifiedUserId, team_id: UUID, game_id: UUID, db: DBSession):
    """Delete a game: the recorder before it is confirmed, the captain any time.

    Args:
        user_id: The verified caller's id.
        team_id: The team.
        game_id: The game.
        db: Request-scoped database session.

    Returns:
        `{"ok": true}`.

    Raises:
        HTTPException: 404 when the caller has no such game; 409 when they may not
            delete it.
    """
    result = service.delete_game(db, user_id, team_id, game_id)
    answer = _game_answer(result, "Whoever recorded a game can delete it before it's confirmed; the captain any time.")
    audit.deletion("game", user_id=user_id, target_id=game_id, detail=str(team_id))
    return answer
