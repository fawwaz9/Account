"""Schemas for the Fitness page beyond teams: gym buddies (Phase 3 item 13)."""
from pydantic import BaseModel, Field


class GymBuddyIn(BaseModel):
    """Request body for saying whether you're looking for someone to train with.

    Attributes:
        looking: Whether you're looking now.
        times: When you could go, up to 80 characters.
        note: Anything else, up to 120 characters.
    """

    looking: bool
    times: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=120)


class GymBuddyOut(BaseModel):
    """A connection who is also looking.

    Attributes:
        name: Their display name.
        times: When they could go.
        note: Anything else they said.
        via: How you know them: "partner" and team names.
    """

    name: str
    times: str | None = None
    note: str | None = None
    via: str


class GymBuddies(BaseModel):
    """Your own gym-buddy status and the connections looking too.

    Attributes:
        looking: Whether you're looking.
        times: When you said you could go.
        note: What else you said.
        buddies: Connections looking too, by name; empty while you aren't looking.
    """

    looking: bool = False
    times: str | None = None
    note: str | None = None
    buddies: list[GymBuddyOut] = []
