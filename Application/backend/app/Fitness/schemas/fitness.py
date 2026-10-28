"""Schemas for the Fitness page beyond teams (Phase 3 items 6-9 and 13).

Activity and goals, gym buddies, team and campus boards, and the league directory.
"""
from datetime import date, datetime
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


class BoardRowOut(BaseModel):
    """One opted-in player on a team's board this week.

    Attributes:
        name: Their display name.
        points: Their points this week.
        is_me: Whether it's you.
    """

    name: str
    points: int
    is_me: bool


class TeamBoard(BaseModel):
    """A team's board this week: opted-in players, seen only by opted-in teammates.

    Attributes:
        opted_in: Whether you've chosen to appear on boards; until then the board is
            empty for you.
        week_start: This week's Monday.
        rows: Opted-in players by points, most first.
    """

    opted_in: bool
    week_start: date
    rows: list[BoardRowOut]


class CampusTeam(BaseModel):
    """A listed team on this week's campus board.

    Attributes:
        team_name: The team's name.
        sport: Its sport.
        points: Its opted-in players' points this week.
    """

    team_name: str
    sport: str | None = None
    points: int


class CampusBoard(BaseModel):
    """This week's campus board, once enough teams are listed.

    Attributes:
        floor: How many listed teams the board waits for.
        week_start: The week counted (Monday, UTC); None while the board is empty.
        teams: Listed teams by points, most first; empty below the floor.
    """

    floor: int
    week_start: date | None = None
    teams: list[CampusTeam]


class DirectoryTeamOut(BaseModel):
    """A listed team in the league directory: never a member's name.

    Attributes:
        team_id: The team, for asking to join.
        name: Its name.
        sport: Its sport.
        level: "casual", "intermediate" or "competitive".
        area: Where it plays.
        looking: Whether it wants players.
        blurb: Its line about itself.
        members: How many are on it, the captain included.
        last_game_on: Its latest recorded game.
        dormant: No game in the last 30 days, so shown greyed.
        mine: Whether you're on it.
        requested: Your request to join it: "pending", "accepted" or "declined".
    """

    team_id: UUID
    name: str
    sport: str | None = None
    level: str | None = None
    area: str | None = None
    looking: bool
    blurb: str | None = None
    members: int
    last_game_on: date | None = None
    dormant: bool
    mine: bool
    requested: str | None = None


class Directory(BaseModel):
    """The league directory, once enough teams are listed.

    Attributes:
        floor: How many listed teams it waits for.
        teams: Listed teams by name; empty below the floor.
    """

    floor: int
    teams: list[DirectoryTeamOut]


class JoinIn(BaseModel):
    """Request body for asking to join a listed team.

    Attributes:
        message: What to tell the captain, up to 200 characters.
    """

    message: str | None = Field(default=None, max_length=200)


class JoinAnswer(BaseModel):
    """Request body for a captain answering a request to join.

    Attributes:
        accept: True puts them on the team; False declines.
    """

    accept: bool


class Status(BaseModel):
    """The outcome of a request, as one word.

    Attributes:
        status: What happened, such as "sent", "accepted" or "declined".
    """

    status: str


class MyJoinRequest(BaseModel):
    """One of your own requests to join a team.

    Attributes:
        id: The request.
        team_name: The team, as it was named when you asked.
        message: What you said.
        status: "pending", "accepted" or "declined".
        created_at: When you asked (naive UTC).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_name: str
    message: str | None = None
    status: str
    created_at: datetime


class TeamJoinRequestOut(BaseModel):
    """A waiting request to join your team, as its captain sees it.

    Attributes:
        request_id: The request, for answering it.
        requester_name: Who asked.
        message: What they said.
        created_at: When they asked (naive UTC).
    """

    request_id: UUID
    requester_name: str
    message: str | None = None
    created_at: datetime
