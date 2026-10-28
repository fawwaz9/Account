"""Schemas for the Fitness page beyond teams: activity, goals (items 6-7), gym buddies (13)."""
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


class ActivityIn(BaseModel):
    """Request body for logging an activity.

    Attributes:
        on_date: The day it happened.
        kind: What it was.
        minutes: How long, 1-600.
        note: Anything about it, up to 120 characters.
    """

    on_date: date
    kind: Literal["walk", "run", "cycle", "swim", "gym", "sport", "yoga", "hike", "other"]
    minutes: int = Field(..., ge=1, le=600)
    note: str | None = Field(default=None, max_length=120)


class Activity(BaseModel):
    """A logged activity and the points it earned.

    Attributes:
        id: The activity.
        on_date: The day it happened.
        kind: What it was.
        minutes: How long.
        points: Points earned, by the formula version it was logged under.
        formula_version: Which formula worked the points out.
        note: Anything about it.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    on_date: date
    kind: str
    minutes: int
    points: int
    formula_version: int
    note: str | None = None


class WeekPoints(BaseModel):
    """One Monday-to-Sunday week's exertion points.

    Attributes:
        week_start: The week's Monday.
        points: Points logged that week.
    """

    week_start: date
    points: int


class GoalSuggestion(BaseModel):
    """A suggested weekly goal and why; advice, never imposed.

    Attributes:
        points: The suggestion; None until there's enough history.
        reason: Why this number, or what's missing.
    """

    points: int | None
    reason: str


class Exertion(BaseModel):
    """This week's points against the goal, the weeks before, and a suggestion.

    Attributes:
        week_start: This week's Monday.
        this_week: Points logged this week so far.
        goal: The weekly goal the user set; None for none.
        suggestion: A suggested goal and why.
        weeks: The 8 weeks before this one, oldest first.
        recent: Activities from the last 28 days, newest first.
    """

    week_start: date
    this_week: int
    goal: int | None
    suggestion: GoalSuggestion
    weeks: list[WeekPoints]
    recent: list[Activity]


class GoalIn(BaseModel):
    """Request body for setting or clearing the weekly goal.

    Attributes:
        goal: Weekly points, 1-10000; None clears it.
    """

    goal: int | None = Field(default=None, ge=1, le=10000)
