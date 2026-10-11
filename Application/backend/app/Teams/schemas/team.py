"""Teams and games (Phase 2 item 11, D26)."""
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.Tasks.schemas.sharing import NewTaskLink as NewLink, TaskLink as Link, TaskMember as Member


def _not_blank(value: str | None, what: str) -> str | None:
    if value is not None and value.strip() == "":
        raise ValueError(f"A {what} can't be blank")
    return value.strip() if value is not None else None


class TeamIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    sport: str | None = Field(default=None, max_length=30)

    @model_validator(mode="after")
    def clean(self):
        self.name = _not_blank(self.name, "team name")
        self.sport = self.sport.strip() or None if self.sport is not None else None
        return self


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    sport: str | None = Field(default=None, max_length=30)

    @model_validator(mode="after")
    def clean(self):
        self.name = _not_blank(self.name, "team name")
        return self


class Record(BaseModel):
    """From confirmed games only."""

    wins: int = 0
    losses: int = 0
    ties: int = 0
    points_for: int = 0
    points_against: int = 0
    #: Recorded but not yet confirmed, or disputed: not in the figures above.
    unconfirmed: int = 0


class TeamSummary(BaseModel):
    team_id: UUID
    name: str
    sport: str | None = None
    captain_name: str
    is_captain: bool
    member_names: list[str]
    record: Record


class GameOut(BaseModel):
    game_id: UUID
    played_on: date
    opponent: str
    our_score: int
    their_score: int
    recorded_by_name: str
    recorded_by_me: bool
    confirmed_by_name: str | None = None
    confirmed_at: datetime | None = None
    disputed_by_name: str | None = None
    disputed_by_me: bool = False
    disputed_our: int | None = None
    disputed_their: int | None = None


class TeamDetail(TeamSummary):
    games: list[GameOut]
    #: The captain's view only: who to take off, and the open link.
    members: list[Member] | None = None
    link: Link | None = None


class GameIn(BaseModel):
    played_on: date
    opponent: str = Field(..., min_length=1, max_length=60)
    our_score: int = Field(..., ge=0, le=999)
    their_score: int = Field(..., ge=0, le=999)

    @model_validator(mode="after")
    def clean(self):
        self.opponent = _not_blank(self.opponent, "opponent")
        return self


class DisputeIn(BaseModel):
    """The score you think it was."""

    our_score: int = Field(..., ge=0, le=999)
    their_score: int = Field(..., ge=0, le=999)


class TeamInvitePreview(BaseModel):
    captain_name: str
    team_name: str
    sport: str | None = None


__all__ = ["DisputeIn", "GameIn", "GameOut", "Link", "Member", "NewLink", "Record", "TeamDetail", "TeamIn",
           "TeamInvitePreview", "TeamSummary", "TeamUpdate"]
