"""Schemas for teams and games on the Fitness page.

Member and link schemas are the shared-task ones, re-exported as `Member`, `Link`
and `NewLink`.
"""
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.Tasks.schemas.sharing import NewTaskLink as NewLink, TaskLink as Link, TaskMember as Member


def _not_blank(value: str | None, what: str) -> str | None:
    """Return a value stripped, None for None, or raise ValueError if it is blank."""
    if value is not None and value.strip() == "":
        raise ValueError(f"A {what} can't be blank")
    return value.strip() if value is not None else None


class TeamIn(BaseModel):
    """Request body for creating a team.

    Attributes:
        name: Team name, 1-60 characters; stripped, not blank.
        sport: Free text, at most 30 characters; blank becomes None.
    """
    name: str = Field(..., min_length=1, max_length=60)
    sport: str | None = Field(default=None, max_length=30)

    @model_validator(mode="after")
    def clean(self):
        """Strip the name and sport, rejecting a blank name.

        Returns:
            The validated model.

        Raises:
            ValueError: If the name is blank (a 422).
        """
        self.name = _not_blank(self.name, "team name")
        self.sport = self.sport.strip() or None if self.sport is not None else None
        return self


class TeamUpdate(BaseModel):
    """Request body for renaming a team or changing its sport; omitted fields stay.

    Attributes:
        name: New name, 1-60 characters; stripped, not blank.
        sport: New sport, at most 30 characters; stored as sent.
    """
    name: str | None = Field(default=None, min_length=1, max_length=60)
    sport: str | None = Field(default=None, max_length=30)

    @model_validator(mode="after")
    def clean(self):
        """Strip a sent name, rejecting a blank one.

        Returns:
            The validated model.

        Raises:
            ValueError: If the name is blank (a 422).
        """
        self.name = _not_blank(self.name, "team name")
        return self


class Record(BaseModel):
    """A team's record, from confirmed games only.

    Attributes:
        wins: Confirmed wins.
        losses: Confirmed losses.
        ties: Confirmed ties.
        points_for: Points scored in confirmed games.
        points_against: Points conceded in confirmed games.
        unconfirmed: Games recorded but not yet confirmed, or disputed; left out of
            the figures above.
    """

    wins: int = 0
    losses: int = 0
    ties: int = 0
    points_for: int = 0
    points_against: int = 0
    #: Recorded but not yet confirmed, or disputed: not in the figures above.
    unconfirmed: int = 0


class TeamSummary(BaseModel):
    """A team as the Fitness page lists it.

    Attributes:
        team_id: The team's id.
        name: Team name.
        sport: Sport, or None.
        captain_name: The captain's display name.
        is_captain: Whether the caller is the captain.
        member_names: Every member's name, in joining order.
        record: The confirmed record.
    """
    team_id: UUID
    name: str
    sport: str | None = None
    captain_name: str
    is_captain: bool
    member_names: list[str]
    record: Record


class GameOut(BaseModel):
    """One game as a player sees it: names, and whether a role is the caller's.

    Attributes:
        game_id: The game's id.
        played_on: Date of the game.
        opponent: Opponent's name.
        our_score: The team's score.
        their_score: The opponent's score.
        recorded_by_name: Who recorded it.
        recorded_by_me: Whether the caller recorded it.
        confirmed_by_name: Who confirmed it, or None while unconfirmed.
        confirmed_at: When it was confirmed (naive UTC), or None.
        disputed_by_name: Who disputes it, or None.
        disputed_by_me: Whether the caller disputes it.
        disputed_our: The disputed version of our score, or None.
        disputed_their: The disputed version of their score, or None.
    """
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
    """A team with its games, plus the captain's management view.

    Attributes:
        games: Every game, newest first.
        members: Members the captain may remove; None for anyone else.
        link: The team's live join link; None for anyone but the captain, or when none
            is live.
    """
    games: list[GameOut]
    #: The captain's view only: who to take off, and the open link.
    members: list[Member] | None = None
    link: Link | None = None


class GameIn(BaseModel):
    """Request body for recording or correcting a game.

    Attributes:
        played_on: Date of the game.
        opponent: Opponent's name, 1-60 characters; stripped, not blank.
        our_score: The team's score, 0-999.
        their_score: The opponent's score, 0-999.
    """
    played_on: date
    opponent: str = Field(..., min_length=1, max_length=60)
    our_score: int = Field(..., ge=0, le=999)
    their_score: int = Field(..., ge=0, le=999)

    @model_validator(mode="after")
    def clean(self):
        """Strip the opponent's name, rejecting a blank one.

        Returns:
            The validated model.

        Raises:
            ValueError: If the opponent is blank (a 422).
        """
        self.opponent = _not_blank(self.opponent, "opponent")
        return self


class DisputeIn(BaseModel):
    """Request body disputing a game with the score the caller believes.

    Attributes:
        our_score: The team's score, 0-999.
        their_score: The opponent's score, 0-999.
    """

    our_score: int = Field(..., ge=0, le=999)
    their_score: int = Field(..., ge=0, le=999)


class TeamInvitePreview(BaseModel):
    """What a team link shows before joining.

    Attributes:
        captain_name: The captain's display name.
        team_name: The team's name.
        sport: The team's sport, or None.
    """
    captain_name: str
    team_name: str
    sport: str | None = None


__all__ = ["DisputeIn", "GameIn", "GameOut", "Link", "Member", "NewLink", "Record", "TeamDetail", "TeamIn",
           "TeamInvitePreview", "TeamSummary", "TeamUpdate"]
