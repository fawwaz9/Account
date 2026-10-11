"""Teams and games (Phase 2 item 11, D26), at /api/teams.

A team you're not on answers 404, the same as one that doesn't exist. The
captain's routes touch only the captain's rows; every game route goes through
the definer functions, the captain's too.
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
NO_TEAM = "Team not found"
NO_GAME = "Game not found"
NO_LINK = "That link has expired or been cancelled."


@router.get("/{user_id}", response_model=list[TeamSummary], responses=responses["user_404"])
def get_teams(user_id: VerifiedUserId, db: DBSession):
    found = service.overview(db, user_id)
    if found is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return found


@router.post("/{user_id}", response_model=TeamDetail, responses=responses["user_404"])
def create_team(user_id: VerifiedUserId, body: TeamIn, db: DBSession):
    made = service.create(db, user_id, body)
    if made is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return made


@router.post("/{user_id}/invites/preview", response_model=TeamInvitePreview, responses=responses["user_404"])
def preview_link(user_id: VerifiedUserId, body: InviteToken, db: DBSession):
    """Whose team this link joins, before you accept. POST, so the token stays
    out of URLs and logs."""
    found = service.preview(db, user_id, body.token)
    if found is None:
        raise HTTPException(status_code=404, detail=NO_LINK)
    return found


@router.post("/{user_id}/invites/accept", response_model=InviteAccepted, responses=responses["user_404"])
def accept_link(user_id: VerifiedUserId, body: InviteToken, db: DBSession):
    return InviteAccepted(status=service.accept(db, user_id, body.token))


@router.get("/{user_id}/{team_id}", response_model=TeamDetail, responses=TEAM_404)
def get_team(user_id: VerifiedUserId, team_id: UUID, db: DBSession):
    found = service.detail(db, user_id, team_id)
    if found is None:
        raise HTTPException(status_code=404, detail=NO_TEAM)
    return found


# ---------------------------------------------------------------- the captain --

@router.patch("/{user_id}/{team_id}", response_model=TeamDetail, responses=TEAM_404)
def update_team(user_id: VerifiedUserId, team_id: UUID, body: TeamUpdate, db: DBSession):
    found = service.update(db, user_id, team_id, body)
    if found is None:
        raise HTTPException(status_code=404, detail=NO_TEAM)
    return found


@router.delete("/{user_id}/{team_id}", responses=TEAM_404)
def delete_team(user_id: VerifiedUserId, team_id: UUID, db: DBSession):
    name = service.delete(db, user_id, team_id)
    if name is None:
        raise HTTPException(status_code=404, detail=NO_TEAM)
    audit.deletion("team", user_id=user_id, target_id=team_id, detail=name)
    return {"deleted": True}


@router.post("/{user_id}/{team_id}/link", response_model=NewLink, responses=TEAM_404)
def make_link(user_id: VerifiedUserId, team_id: UUID, db: DBSession):
    link = service.new_link(db, user_id, team_id)
    if link is None:
        raise HTTPException(status_code=404, detail=NO_TEAM)
    return link


@router.delete("/{user_id}/{team_id}/link", responses=TEAM_404)
def cancel_link(user_id: VerifiedUserId, team_id: UUID, db: DBSession):
    if not service.cancel_link(db, user_id, team_id):
        raise HTTPException(status_code=404, detail=NO_TEAM)
    return {"cancelled": True}


@router.delete("/{user_id}/{team_id}/members/{member_id}", responses=TEAM_404)
def remove_member(user_id: VerifiedUserId, team_id: UUID, member_id: UUID, db: DBSession):
    if not service.remove_member(db, user_id, team_id, member_id):
        raise HTTPException(status_code=404, detail="Nobody by that id is on this team")
    audit.deletion("team_member", user_id=user_id, target_id=member_id, detail=str(team_id))
    return {"removed": True}


# ------------------------------------------------------------ anyone on it --

@router.delete("/{user_id}/{team_id}/membership", responses=TEAM_404)
def leave_team(user_id: VerifiedUserId, team_id: UUID, db: DBSession):
    if not service.leave(db, user_id, team_id):
        raise HTTPException(status_code=404, detail=NO_TEAM)
    return {"left": True}


@router.post("/{user_id}/{team_id}/games", response_model=TeamDetail, responses=TEAM_404)
def record_game(user_id: VerifiedUserId, team_id: UUID, body: GameIn, db: DBSession):
    found = service.record_game(db, user_id, team_id, body)
    if found is None:
        raise HTTPException(status_code=404, detail=NO_TEAM)
    return found


def _game_answer(result: bool | None, refused: str):
    if result is None:
        raise HTTPException(status_code=404, detail=NO_GAME)
    if result is False:
        raise HTTPException(status_code=409, detail=refused)
    return {"ok": True}


@router.put("/{user_id}/{team_id}/games/{game_id}", responses=GAME_BOTH)
def correct_game(user_id: VerifiedUserId, team_id: UUID, game_id: UUID, body: GameIn, db: DBSession):
    return _game_answer(service.correct_game(db, user_id, team_id, game_id, body),
                        "Only whoever recorded a game can correct it, and only before it's confirmed.")


@router.post("/{user_id}/{team_id}/games/{game_id}/confirm", responses=GAME_BOTH)
def confirm_game(user_id: VerifiedUserId, team_id: UUID, game_id: UUID, db: DBSession):
    return _game_answer(service.confirm_game(db, user_id, team_id, game_id),
                        "Someone other than whoever recorded it confirms a game, once, and not while it's disputed.")


@router.post("/{user_id}/{team_id}/games/{game_id}/dispute", responses=GAME_BOTH)
def dispute_game(user_id: VerifiedUserId, team_id: UUID, game_id: UUID, body: DisputeIn, db: DBSession):
    return _game_answer(service.dispute_game(db, user_id, team_id, game_id, body),
                        "Someone other than whoever recorded it can dispute a game, before it's confirmed.")


@router.delete("/{user_id}/{team_id}/games/{game_id}", responses=GAME_BOTH)
def delete_game(user_id: VerifiedUserId, team_id: UUID, game_id: UUID, db: DBSession):
    result = service.delete_game(db, user_id, team_id, game_id)
    answer = _game_answer(result, "Whoever recorded a game can delete it before it's confirmed; the captain any time.")
    audit.deletion("game", user_id=user_id, target_id=game_id, detail=str(team_id))
    return answer
