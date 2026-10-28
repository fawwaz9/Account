"""Response bodies for shared events: the owner's view and the member's.

The owner-side shapes are a shared task's, re-exported from
`Tasks.schemas.sharing` as `Member`, `Link` and `NewLink`. A member sees when and
where an event is, never its course.
"""
from datetime import date, time
from uuid import UUID

from pydantic import BaseModel

from app.Tasks.schemas.sharing import NewTaskLink as NewLink, TaskLink as Link, TaskMember as Member


class EventSharing(BaseModel):
    """Who is on one of your events, and whether an invite link is open.

    Attributes:
        members: Everyone who joined, earliest first.
        link: The newest live link; None when none is open.
        shareable: False for a repeating event, a shift, or a block a grade
            produced; only one-off events can be shared.
        max_members: The most people the event can hold besides its owner.
    """

    members: list[Member]
    link: Link | None = None
    #: False for a repeat, a shift, or a block a grade produced.
    shareable: bool
    max_members: int


class SharedEvent(BaseModel):
    """Someone else's event you are on: when and where, never the course.

    Attributes:
        event_id: The event's id.
        owner_name: The owner's name, copied when you joined.
        title: The event's title.
        kind: The event's kind, as its stored string.
        location: Where it happens.
        notes: The event's notes.
        starts_on: The date it happens.
        start_time: Local start time; None for an all-day event.
        end_time: Local end time; None when it has none.
        member_names: Everyone on it besides the owner, you included.
    """

    event_id: UUID
    owner_name: str
    title: str
    kind: str
    location: str | None = None
    notes: str | None = None
    starts_on: date
    start_time: time | None = None
    end_time: time | None = None
    #: Everyone on it besides the owner, you included.
    member_names: list[str]


class EventInvitePreview(BaseModel):
    """What the holder of an event link sees before accepting it.

    Attributes:
        owner_name: Who owns the event.
        title: The event's title.
        starts_on: The date it happens.
    """

    owner_name: str
    title: str
    starts_on: date


__all__ = ["EventSharing", "EventInvitePreview", "Link", "Member", "NewLink", "SharedEvent"]
