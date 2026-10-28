"""Shared-event routes under /api/calendar: owner controls and the member's view.

The owner's routes act on the owner's own event. The member's routes reach
someone else's event only through the definer functions in `sharing`, to see it
or leave it, so an event the caller is not on answers 404 like a missing one.
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
    """Get who is on one of the caller's events and whether an invite link is open.

    Args:
        user_id: The verified caller's id.
        event_id: The event.
        db: Request-scoped database session.

    Returns:
        The members, the live link (without its token) and whether it can be shared.

    Raises:
        HTTPException: 404 if the event is missing or not the caller's.
    """
    found = service.sharing_of(db, user_id, event_id)
    if found is None:
        raise HTTPException(status_code=404, detail=NO_EVENT)
    return found


@router.post("/{user_id}/events/{event_id}/sharing/link", response_model=NewLink,
             responses={**EVENT_404, 400: {"description": "This event can't be shared"}})
def make_link(user_id: VerifiedUserId, event_id: UUID, db: DBSession):
    """Make a new invite link for one of the caller's events, cancelling any live one.

    Args:
        user_id: The verified caller's id.
        event_id: The event.
        db: Request-scoped database session.

    Returns:
        The link's token, shown only this once, and when it expires.

    Raises:
        HTTPException: 400 if the event repeats, is a shift, or came from a grade;
            404 if the event is missing or not the caller's.
    """
    try:
        link = service.new_link(db, user_id, event_id)
    except service.NotShareable as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if link is None:
        raise HTTPException(status_code=404, detail=NO_EVENT)
    return link


@router.delete("/{user_id}/events/{event_id}/sharing/link", responses=EVENT_404)
def cancel_link(user_id: VerifiedUserId, event_id: UUID, db: DBSession):
    """Cancel any live invite link on one of the caller's events.

    Args:
        user_id: The verified caller's id.
        event_id: The event.
        db: Request-scoped database session.

    Returns:
        `{"cancelled": true}`, including when no link was open.

    Raises:
        HTTPException: 404 if the event is missing or not the caller's.
    """
    if not service.cancel_link(db, user_id, event_id):
        raise HTTPException(status_code=404, detail=NO_EVENT)
    return {"cancelled": True}


@router.delete("/{user_id}/events/{event_id}/sharing/members/{member_id}", responses=EVENT_404)
def remove_member(user_id: VerifiedUserId, event_id: UUID, member_id: UUID, db: DBSession):
    """Take someone off one of the caller's events.

    Args:
        user_id: The verified caller's id.
        event_id: The event.
        member_id: The membership's id, as `get_sharing` lists it.
        db: Request-scoped database session.

    Returns:
        `{"removed": true}`.

    Raises:
        HTTPException: 404 if the event is not the caller's or has no such member.
    """
    if not service.remove_member(db, user_id, event_id, member_id):
        raise HTTPException(status_code=404, detail="Nobody by that id is on this event")
    audit.deletion("event_member", user_id=user_id, target_id=member_id, detail=str(event_id))
    return {"removed": True}


# --------------------------------------------------------------- the member --

@router.get("/{user_id}/shared-events", response_model=list[SharedEvent], responses=responses["user_404"])
def get_shared_events(user_id: VerifiedUserId, db: DBSession, start: date | None = None, end: date | None = None):
    """List other people's events the caller has joined, soonest first.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        start: Earliest event date to include; omit for no lower bound.
        end: Latest event date to include; omit for no upper bound.

    Returns:
        The member's view of each event; empty when there are none.
    """
    return service.shared_with_me(db, user_id, start, end)


@router.post("/{user_id}/shared-events/invites/preview", response_model=EventInvitePreview,
             responses=responses["user_404"])
def preview_link(user_id: VerifiedUserId, body: InviteToken, db: DBSession):
    """See whose event an invite link joins, before accepting it.

    POST so the token stays out of URLs and logs.

    Args:
        user_id: The verified caller's id.
        body: The token from the link.
        db: Request-scoped database session.

    Returns:
        The owner's name and the event's title and date.

    Raises:
        HTTPException: 404 if the link is unknown, expired or cancelled, or the
            event can no longer be shared.
    """
    found = service.preview(db, user_id, body.token)
    if found is None:
        raise HTTPException(status_code=404, detail=NO_LINK)
    return found


@router.post("/{user_id}/shared-events/invites/accept", response_model=InviteAccepted,
             responses=responses["user_404"])
def accept_link(user_id: VerifiedUserId, body: InviteToken, db: DBSession):
    """Join someone else's event through an invite link.

    Args:
        user_id: The verified caller's id.
        body: The token from the link.
        db: Request-scoped database session.

    Returns:
        The outcome: "accepted", "invalid", "own", "already" or "full".
    """
    return InviteAccepted(status=service.accept(db, user_id, body.token))


@router.delete("/{user_id}/shared-events/{event_id}", responses=EVENT_404)
def leave_shared_event(user_id: VerifiedUserId, event_id: UUID, db: DBSession):
    """Leave someone else's event the caller is on.

    Args:
        user_id: The verified caller's id.
        event_id: The event.
        db: Request-scoped database session.

    Returns:
        `{"left": true}`.

    Raises:
        HTTPException: 404 if the caller is not on the event.
    """
    if not service.leave(db, user_id, event_id):
        raise HTTPException(status_code=404, detail=NO_EVENT)
    return {"left": True}
