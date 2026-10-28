"""Request and response bodies for shared tasks: the owner's view and the member's.

An owner shares a one-off task through an invite link; members see a few of its
fields and may tick it off or edit its text. `task_sharing_service` builds
these, and shared events reuse the owner-side shapes.
"""
from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class TaskMember(BaseModel):
    """Someone on one of your tasks, as the owner sees them.

    Attributes:
        id: The membership's id, used to remove them; not their user id.
        name: The member's name, copied when they joined.
        joined_at: When they joined, naive UTC.
    """

    id: UUID
    name: str
    joined_at: datetime


class TaskLink(BaseModel):
    """The live invite link on one of your tasks, without its token.

    Attributes:
        expires_at: When the link stops working, naive UTC.
    """

    expires_at: datetime


class TaskSharing(BaseModel):
    """Who is on one of your tasks, and whether an invite link is open.

    Attributes:
        members: Everyone who joined, earliest first.
        link: The newest live link; None when none is open.
        shareable: False for an occurrence of a repeating task, which cannot be
            shared.
        max_members: The most people the task can hold besides its owner.
    """

    members: list[TaskMember]
    link: TaskLink | None = None
    #: False for a repeating occurrence, which cannot be shared.
    shareable: bool
    max_members: int


class NewTaskLink(BaseModel):
    """A link just made, carrying its token; the token is never shown again.

    Attributes:
        token: The secret for the invite URL's fragment; only its SHA-256 is stored.
        expires_at: When the link stops working, naive UTC.
    """

    token: str
    expires_at: datetime


class SharedTask(BaseModel):
    """Someone else's task you are on, limited to the fields a member may see.

    Attributes:
        task_id: The task's id.
        owner_name: The owner's name, copied when you joined.
        title: The task's title.
        notes: The task's notes.
        due_date: When it is due; None for no date.
        due_time: Local time it is due; None means the end of the day.
        done: Whether it is ticked off.
        completed_at: When it was ticked off, naive UTC.
        member_names: Everyone on it besides the owner, you included.
    """

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
    """Request body for a member's change to a shared task; omitted fields stay.

    Attributes:
        done: Tick or untick the task; null leaves it as it is.
        title: New title, 1-200 characters and not blank; null keeps the current one.
        notes: New notes, up to 2000 characters; null clears them.
    """

    done: bool | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_update(self):
        """Refuse a title that is only whitespace.

        Returns:
            The validated model.

        Raises:
            ValueError: If `title` is given and blank.
        """
        if self.title is not None and self.title.strip() == "":
            raise ValueError("A task needs a title")
        return self


class TaskInviteToken(BaseModel):
    """Request body carrying the token from an invite link.

    Attributes:
        token: The token as it appeared in the link's fragment, 1-200 characters.
    """

    token: str = Field(..., min_length=1, max_length=200)


class TaskInvitePreview(BaseModel):
    """What the holder of a task link sees before accepting it.

    Attributes:
        owner_name: Who owns the task.
        title: The task's title.
    """

    owner_name: str
    title: str


class TaskInviteAccepted(BaseModel):
    """The outcome of accepting a task link.

    Attributes:
        status: "accepted"; "invalid" for an unknown, expired or revoked link (or
            a task whose owner is gone); "own" for your own task; "already" when
            you are on it; "full" at the member limit.
    """

    #: accepted | invalid | own | already | full
    status: str
