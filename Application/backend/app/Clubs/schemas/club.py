"""Schemas for clubs (Phase 3 item 10): members by link, posts, polls and events.

Member and link schemas are the shared-task ones, as teams use them.
"""
from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.Tasks.schemas.sharing import NewTaskLink as NewLink, TaskLink as Link, TaskMember as Member  # noqa: F401


def _not_blank(value: str | None, what: str) -> str | None:
    """Return a value stripped, None for None, or raise ValueError if it is blank."""
    if value is None:
        return None
    if value.strip() == "":
        raise ValueError(f"A {what} can't be blank")
    return value.strip()


class ClubIn(BaseModel):
    """Request body for making a club.

    Attributes:
        name: Its name, 1-80 characters; stripped, not blank.
        about: A line about it, up to 300 characters; blank becomes None.
    """

    name: str = Field(..., min_length=1, max_length=80)
    about: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def clean(self):
        """Strip the name and about line, rejecting a blank name.

        Returns:
            The validated model.

        Raises:
            ValueError: If the name is blank (a 422).
        """
        self.name = _not_blank(self.name, "club name")
        self.about = (self.about or "").strip() or None
        return self


class ClubUpdate(BaseModel):
    """Request body for renaming a club or changing its line; omitted fields stay.

    Attributes:
        name: New name, 1-80 characters; stripped, not blank.
        about: New line, up to 300 characters; blank clears it.
    """

    name: str | None = Field(default=None, min_length=1, max_length=80)
    about: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def clean(self):
        """Strip a sent name, rejecting a blank one.

        Returns:
            The validated model.

        Raises:
            ValueError: If the name is blank (a 422).
        """
        self.name = _not_blank(self.name, "club name")
        return self


class ClubSummary(BaseModel):
    """A club as listed: its name, owner and size.

    Attributes:
        club_id: The club.
        name: Its name.
        about: Its line about itself.
        owner_name: The owner's name.
        is_owner: Whether it's the caller's own club.
        member_count: How many are in it, the owner included.
    """

    club_id: UUID
    name: str
    about: str | None = None
    owner_name: str
    is_owner: bool
    member_count: int


class PostIn(BaseModel):
    """Request body for an announcement.

    Attributes:
        body: Its text, 1-1000 characters; stripped, not blank.
    """

    body: str = Field(..., min_length=1, max_length=1000)

    @model_validator(mode="after")
    def clean(self):
        """Strip the text, rejecting a blank one.

        Returns:
            The validated model.

        Raises:
            ValueError: If it is blank (a 422).
        """
        self.body = _not_blank(self.body, "post")
        return self


class PostOut(BaseModel):
    """An announcement in a club.

    Attributes:
        post_id: The post.
        body: Its text.
        created_at: When it was posted (naive UTC).
    """

    post_id: UUID
    body: str
    created_at: datetime


class PollIn(BaseModel):
    """Request body for a poll.

    Attributes:
        question: The question, 1-200 characters.
        options: 2-6 choices, each 1-80 characters, stripped and not blank.
        closes_on: The last day votes count; None for no end.
    """

    question: str = Field(..., min_length=1, max_length=200)
    options: list[str] = Field(..., min_length=2, max_length=6)
    closes_on: date | None = None

    @model_validator(mode="after")
    def clean(self):
        """Strip the question and choices, rejecting blank or overlong ones.

        Returns:
            The validated model.

        Raises:
            ValueError: If the question or a choice is blank, a choice is over 80
                characters, or two choices are the same (a 422).
        """
        self.question = _not_blank(self.question, "question")
        cleaned = [_not_blank(option, "choice") for option in self.options]
        if any(len(option) > 80 for option in cleaned):
            raise ValueError("A choice can be at most 80 characters")
        if len({option.lower() for option in cleaned}) != len(cleaned):
            raise ValueError("Two choices are the same")
        self.options = cleaned
        return self


class PollOut(BaseModel):
    """A poll as someone in the club sees it: counts, never who voted for what.

    Attributes:
        poll_id: The poll.
        question: The question.
        options: The choices.
        closes_on: The last day votes count, or None.
        counts: Votes per choice, in order.
        my_vote: Your choice, or None.
        open: Whether votes still count.
    """

    poll_id: UUID
    question: str
    options: list[str]
    closes_on: date | None = None
    counts: list[int]
    my_vote: int | None = None
    open: bool


class VoteIn(BaseModel):
    """Request body for voting in a poll.

    Attributes:
        option: The choice's position, from 0.
    """

    option: int = Field(..., ge=0, le=5)


class ClubEventIn(BaseModel):
    """Request body for a club event.

    Attributes:
        title: What it is, 1-80 characters.
        on_date: The day.
        start_time: When it starts; None for all day.
        end_time: When it ends; needs a start, and must be after it.
        location: Where, up to 80 characters.
    """

    title: str = Field(..., min_length=1, max_length=80)
    on_date: date
    start_time: time | None = None
    end_time: time | None = None
    location: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def clean(self):
        """Strip the title and place, and check the times fit together.

        Returns:
            The validated model.

        Raises:
            ValueError: If the title is blank, an end has no start, or ends before it
                starts (a 422).
        """
        self.title = _not_blank(self.title, "title")
        self.location = (self.location or "").strip() or None
        if self.end_time is not None and self.start_time is None:
            raise ValueError("An end time needs a start time")
        if self.end_time is not None and self.end_time <= self.start_time:
            raise ValueError("An event has to end after it starts")
        return self


class ClubEventOut(BaseModel):
    """A club event.

    Attributes:
        event_id: The event.
        title: What it is.
        on_date: The day.
        start_time: When it starts, or None for all day.
        end_time: When it ends, or None.
        location: Where, or None.
    """

    event_id: UUID
    title: str
    on_date: date
    start_time: time | None = None
    end_time: time | None = None
    location: str | None = None


class CalendarClubEvent(ClubEventOut):
    """A club event as the calendar shows it, with its club.

    Attributes:
        club_id: Its club.
        club_name: Its club's name.
    """

    club_id: UUID
    club_name: str


class ClubDetail(ClubSummary):
    """A club with its posts, polls and upcoming events, plus the owner's management view.

    Attributes:
        posts: Announcements, newest first.
        polls: Polls, newest first.
        events: Events from today on, soonest first.
        members: Members the owner may remove; None for anyone else.
        link: The club's live join link; None for anyone but the owner, or none live.
    """

    posts: list[PostOut]
    polls: list[PollOut]
    events: list[ClubEventOut]
    members: list[Member] | None = None
    link: Link | None = None


class ClubInvitePreview(BaseModel):
    """What a club link shows before it is accepted.

    Attributes:
        owner_name: The owner's name.
        club_name: The club's name.
    """

    owner_name: str
    club_name: str
