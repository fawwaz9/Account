"""Shared events (Phase 2 item 9b, D24), under /api/calendar beside the rest.

The owner's routes hang off the owner's own event. The member's routes reach
someone else's event only through the definer functions in ``sharing``, and
only to see it or leave it -- so an event you are not on answers 404, the same
as one that does not exist.
"""
from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Calendar.schemas.sharing import EventInvitePreview, EventSharing, NewLink, SharedEvent
from app.Calendar.services import event_sharing_service as service
from app.Tasks.schemas.sharing import TaskInviteAccepted as InviteAccepted, TaskInviteToken as InviteToken
from app.shared import audit
from app.shared.errors import responses

router = APIRouter()

EVENT_404 = {404: {"description": "Event not found"}}
NO_EVENT = "Event not found"
NO_LINK = "That link has expired or been cancelled."


# ---------------------------------------------------------------- the owner --

@router.get("/{user_id}/events/{event_id}/sharing", response_model=EventSharing, responses=EVENT_404)
def get_sharing(user_id: VerifiedUserId, event_id: UUID, db: DBSession):
    found = service.sharing_of(db, user_id, event_id)
    if found is None:
        raise HTTPException(status_code=404, detail=NO_EVENT)
    return found


@router.post("/{user_id}/events/{event_id}/sharing/link", response_model=NewLink,
             responses={**EVENT_404, 400: {"description": "This event can't be shared"}})
def make_link(user_id: VerifiedUserId, event_id: UUID, db: DBSession):
    try:
        link = service.new_link(db, user_id, event_id)
    except service.NotShareable as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if link is None:
        raise HTTPException(status_code=404, detail=NO_EVENT)
    return link


@router.delete("/{user_id}/events/{event_id}/sharing/link", responses=EVENT_404)
def cancel_link(user_id: VerifiedUserId, event_id: UUID, db: DBSession):
    if not service.cancel_link(db, user_id, event_id):
        raise HTTPException(status_code=404, detail=NO_EVENT)
    return {"cancelled": True}


@router.delete("/{user_id}/events/{event_id}/sharing/members/{member_id}", responses=EVENT_404)
def remove_member(user_id: VerifiedUserId, event_id: UUID, member_id: UUID, db: DBSession):
    if not service.remove_member(db, user_id, event_id, member_id):
        raise HTTPException(status_code=404, detail="Nobody by that id is on this event")
    audit.deletion("event_member", user_id=user_id, target_id=member_id, detail=str(event_id))
    return {"removed": True}


# --------------------------------------------------------------- the member --

@router.get("/{user_id}/shared-events", response_model=list[SharedEvent], responses=responses["user_404"])
def get_shared_events(user_id: VerifiedUserId, db: DBSession, start: date | None = None, end: date | None = None):
    return service.shared_with_me(db, user_id, start, end)


@router.post("/{user_id}/shared-events/invites/preview", response_model=EventInvitePreview,
             responses=responses["user_404"])
def preview_link(user_id: VerifiedUserId, body: InviteToken, db: DBSession):
    """Whose event this link joins, before you accept. POST, so the token stays
    out of URLs and logs."""
    found = service.preview(db, user_id, body.token)
    if found is None:
        raise HTTPException(status_code=404, detail=NO_LINK)
    return found


@router.post("/{user_id}/shared-events/invites/accept", response_model=InviteAccepted,
             responses=responses["user_404"])
def accept_link(user_id: VerifiedUserId, body: InviteToken, db: DBSession):
    return InviteAccepted(status=service.accept(db, user_id, body.token))


@router.delete("/{user_id}/shared-events/{event_id}", responses=EVENT_404)
def leave_shared_event(user_id: VerifiedUserId, event_id: UUID, db: DBSession):
    if not service.leave(db, user_id, event_id):
        raise HTTPException(status_code=404, detail=NO_EVENT)
    return {"left": True}
