"""Shared tasks (Phase 2 item 9a, D23): the owner's view and the member's."""
from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class TaskMember(BaseModel):
    """Someone on one of your tasks, as the owner sees them."""

    id: UUID
    name: str
    joined_at: datetime


class TaskLink(BaseModel):
    """The live link on one of your tasks. Its token was shown once, when made."""

    expires_at: datetime


class TaskSharing(BaseModel):
    """Who is on one of your tasks, and whether a link is open."""

    members: list[TaskMember]
    link: TaskLink | None = None
    #: False for a repeating occurrence, which cannot be shared.
    shareable: bool
    max_members: int


class NewTaskLink(BaseModel):
    """A link just made. The token is in it, and is never shown again."""

    token: str
    expires_at: datetime


class SharedTask(BaseModel):
    """Someone else's task you are on: the few fields a member may see."""

    task_id: UUID
    owner_name: str
    title: str
    notes: str | None = None
    due_date: date | None = None
    due_time: time | None = None
    done: bool
    completed_at: datetime | None = None
    #: Everyone on it besides the owner, you included.
    member_names: list[str]


class SharedTaskUpdate(BaseModel):
    """What a member may change: whether it is done, and its text."""

    done: bool | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_update(self):
        if self.title is not None and self.title.strip() == "":
            raise ValueError("A task needs a title")
        return self


class TaskInviteToken(BaseModel):
    token: str = Field(..., min_length=1, max_length=200)


class TaskInvitePreview(BaseModel):
    owner_name: str
    title: str


class TaskInviteAccepted(BaseModel):
    #: accepted | invalid | own | already | full
    status: str
