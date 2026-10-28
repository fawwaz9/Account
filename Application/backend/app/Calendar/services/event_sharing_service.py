"""Service functions for shared calendar events: the owner's side and the member's.

The owner's functions touch only the owner's own rows (the event, its members
and its invite link) under the ordinary row policy. The member's functions go
entirely through `app._database.sharing`, whose definer functions are the only
way to reach someone else's event; a member can see an event and leave it.
"""
import hashlib
import secrets
import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app._database import sharing
from app._database.models import INVITE_DAYS, MAX_EVENT_MEMBERS, EventInviteModel, EventMemberModel, EventModel, utc_now
from app.Calendar.schemas.sharing import EventInvitePreview, EventSharing, Link, Member, NewLink, SharedEvent


class NotShareable(ValueError):
    """Raised when a link is asked for on an event that cannot be shared."""

    pass


def token_hash(token: str) -> str:
    """Return the SHA-256 hex digest of an invite token, the only form ever stored.

    Args:
        token: The raw token from the link.

    Returns:
        The 64-character hex digest.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def _own_event(db: Session, user_id: uuid.UUID, event_id: uuid.UUID) -> EventModel | None:
    """Return the caller's own event with this id, or None."""
    return db.query(EventModel).filter(EventModel.id == event_id, EventModel.user_id == user_id).first()


def _live_links(db: Session, event_id: uuid.UUID):
    """Query the event's invite links that are neither revoked nor expired."""
    return db.query(EventInviteModel).filter(
        EventInviteModel.event_id == event_id, EventInviteModel.revoked_at.is_(None),
        EventInviteModel.expires_at > utc_now(),
    )


# ---------------------------------------------------------------- the owner --

def sharing_of(db: Session, user_id: uuid.UUID, event_id: uuid.UUID) -> EventSharing | None:
    """Return who is on one of the caller's events and whether a link is open.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        event_id: The event.

    Returns:
        Its members (earliest first), the newest live link, whether it can be
        shared and the member limit; None when the event is not the caller's.
    """
    event = _own_event(db, user_id, event_id)
    if event is None:
        return None
    members = (
        db.query(EventMemberModel).filter(EventMemberModel.event_id == event.id)
        .order_by(EventMemberModel.joined_at).all()
    )
    link = _live_links(db, event.id).order_by(EventInviteModel.created_at.desc()).first()
    return EventSharing(
        members=[Member(id=m.id, name=m.member_name, joined_at=m.joined_at) for m in members],
        link=Link(expires_at=link.expires_at) if link else None,
        shareable=sharing.event_shareable(event),
        max_members=MAX_EVENT_MEMBERS,
    )


def new_link(db: Session, user_id: uuid.UUID, event_id: uuid.UUID) -> NewLink | None:
    """Make a fresh invite link for one of the caller's events, cancelling any live one.

    Commits.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        event_id: The event to share.

    Returns:
        The new link with its token, which is never shown again; None when the
        event is not the caller's.

    Raises:
        NotShareable: If the event repeats, is a shift, or was produced by a grade.
    """
    event = _own_event(db, user_id, event_id)
    if event is None:
        return None
    if not sharing.event_shareable(event):
        raise NotShareable("Only a one-off event of your own can be shared: not a repeat, a shift, or a grade's.")
    now = utc_now()
    for old in _live_links(db, event.id):
        old.revoked_at = now
    token = secrets.token_urlsafe(24)
    link = EventInviteModel(id=uuid.uuid4(), event_id=event.id, token_hash=token_hash(token),
                            created_at=now, expires_at=now + timedelta(days=INVITE_DAYS))
    db.add(link)
    db.commit()
    return NewLink(token=token, expires_at=link.expires_at)


def cancel_link(db: Session, user_id: uuid.UUID, event_id: uuid.UUID) -> bool:
    """Revoke every live invite link on one of the caller's events.

    Commits; members who already joined stay.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        event_id: The event.

    Returns:
        True, including when no link was open; False when the event is not the
        caller's.
    """
    event = _own_event(db, user_id, event_id)
    if event is None:
        return False
    now = utc_now()
    for old in _live_links(db, event.id):
        old.revoked_at = now
    db.commit()
    return True


def remove_member(db: Session, user_id: uuid.UUID, event_id: uuid.UUID, member_id: uuid.UUID) -> bool:
    """Take someone off one of the caller's events.

    Commits.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        event_id: The event.
        member_id: The membership row's id, not the member's user id.

    Returns:
        True when removed; False when the event is not the caller's or has no
        such member.
    """
    event = _own_event(db, user_id, event_id)
    if event is None:
        return False
    member = db.query(EventMemberModel).filter(
        EventMemberModel.id == member_id, EventMemberModel.event_id == event.id,
    ).first()
    if member is None:
        return False
    db.delete(member)
    db.commit()
    return True


# --------------------------------------------------------------- the member --

def shared_with_me(db: Session, user_id: uuid.UUID, start: date | None = None,
                   end: date | None = None) -> list[SharedEvent]:
    """Return the events the caller has joined as a member, soonest first.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        start: Earliest event date to include; None for no lower bound.
        end: Latest event date to include; None for no upper bound.

    Returns:
        The member's view of each event, ordered by date, start time (untimed
        last) and title; empty when there are none.
    """
    rows = [
        r for r in sharing.shared_events(db, user_id)
        if (start is None or r.starts_on >= start) and (end is None or r.starts_on <= end)
    ]
    rows.sort(key=lambda r: (r.starts_on, r.start_time is None, r.start_time or 0, r.title.lower()))
    return [
        SharedEvent(event_id=r.event_id, owner_name=r.owner_name, title=r.title, kind=r.kind,
                    location=r.location, notes=r.notes, starts_on=r.starts_on, start_time=r.start_time,
                    end_time=r.end_time, member_names=r.member_names)
        for r in rows
    ]


def leave(db: Session, user_id: uuid.UUID, event_id: uuid.UUID) -> bool:
    """Take the caller off someone else's event.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        event_id: The event.

    Returns:
        True when the caller was on it and has left; False otherwise.
    """
    return sharing.leave_shared_event(db, user_id, event_id)


def preview(db: Session, user_id: uuid.UUID, token: str) -> EventInvitePreview | None:
    """Return what the holder of an event link sees before accepting it.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        token: The raw token from the link.

    Returns:
        The owner's name and the event's title and date; None when the link is
        unknown, revoked or expired, the event cannot be shared, or its owner's
        account is being deleted.
    """
    found = sharing.event_invite_preview(db, user_id, token_hash(token))
    return EventInvitePreview(owner_name=found.owner_name, title=found.title, starts_on=found.starts_on) if found else None


def accept(db: Session, user_id: uuid.UUID, token: str) -> str:
    """Join someone else's event through its invite link.

    Commits on success.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        token: The raw token from the link.

    Returns:
        "accepted", "invalid", "own", "already" or "full".
    """
    return sharing.accept_event_invite(db, user_id, token_hash(token))
