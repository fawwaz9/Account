"""Accountability partners and invites (Phase 2 item 10, D22)."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class Figure(BaseModel):
    """Completion, never outcomes: the share of this week's tasks done, and how
    many good weeks in a row (80% or more). As of ``figure_on``."""

    week_percent: float | None
    streak_weeks: int
    figure_on: date | None


class Partner(BaseModel):
    partner_id: UUID
    name: str
    since: datetime
    #: None until they have opened the app since the partnership started.
    figure: Figure | None = None


class OpenInvite(BaseModel):
    id: UUID
    created_at: datetime
    expires_at: datetime


class Partners(BaseModel):
    mine: Figure
    partners: list[Partner]
    invites: list[OpenInvite]


class NewInvite(BaseModel):
    """The token is shown once, here; only its hash is kept."""

    id: UUID
    token: str
    expires_at: datetime


class InviteToken(BaseModel):
    token: str = Field(..., min_length=16, max_length=100)


class InvitePreviewOut(BaseModel):
    inviter_name: str
    kind: str


class AcceptResult(BaseModel):
    status: Literal["accepted", "invalid", "own", "already"]
