"""Shared events (Phase 2 item 9b, D24).

The same split as shared tasks: the owner's half touches only the owner's own
rows, inside the ordinary row policy; the member's half goes entirely through
``sharing``. A member sees an event and may leave it -- nothing more.
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
    pass


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _own_event(db: Session, user_id: uuid.UUID, event_id: uuid.UUID) -> EventModel | None:
    return db.query(EventModel).filter(EventModel.id == event_id, EventModel.user_id == user_id).first()


def _live_links(db: Session, event_id: uuid.UUID):
    return db.query(EventInviteModel).filter(
        EventInviteModel.event_id == event_id, EventInviteModel.revoked_at.is_(None),
        EventInviteModel.expires_at > utc_now(),
    )


# ---------------------------------------------------------------- the owner --

def sharing_of(db: Session, user_id: uuid.UUID, event_id: uuid.UUID) -> EventSharing | None:
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
    """A fresh link, cancelling any live one: one link per event at a time."""
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
    event = _own_event(db, user_id, event_id)
    if event is None:
        return False
    now = utc_now()
    for old in _live_links(db, event.id):
        old.revoked_at = now
    db.commit()
    return True


def remove_member(db: Session, user_id: uuid.UUID, event_id: uuid.UUID, member_id: uuid.UUID) -> bool:
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
    """The events you are on, optionally within a window, soonest first."""
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
    return sharing.leave_shared_event(db, user_id, event_id)


def preview(db: Session, user_id: uuid.UUID, token: str) -> EventInvitePreview | None:
    found = sharing.event_invite_preview(db, user_id, token_hash(token))
    return EventInvitePreview(owner_name=found.owner_name, title=found.title, starts_on=found.starts_on) if found else None


def accept(db: Session, user_id: uuid.UUID, token: str) -> str:
    return sharing.accept_event_invite(db, user_id, token_hash(token))
