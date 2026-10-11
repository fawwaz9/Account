"""Shared events (Phase 2 item 9b, D24): the owner's view and the member's.

The owner's shapes are the same as a shared task's, so they are reused.
"""
from datetime import date, time
from uuid import UUID

from pydantic import BaseModel

from app.Tasks.schemas.sharing import NewTaskLink as NewLink, TaskLink as Link, TaskMember as Member


class EventSharing(BaseModel):
    """Who is on one of your events, and whether a link is open."""

    members: list[Member]
    link: Link | None = None
    #: False for a repeat, a shift, or a block a grade produced.
    shareable: bool
    max_members: int


class SharedEvent(BaseModel):
    """Someone else's event you are on: when and where, never the course."""

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
    owner_name: str
    title: str
    starts_on: date


__all__ = ["EventSharing", "EventInvitePreview", "Link", "Member", "NewLink", "SharedEvent"]
