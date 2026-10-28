"""Schemas for accountability partners and partner invites."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class Figure(BaseModel):
    """A weekly completion figure: completion only, never grades or money.

    Attributes:
        week_percent: Share of this week's tasks done, 0-100; None when nothing was due.
        streak_weeks: Good weeks (80% or more) in a row before this one.
        figure_on: The owner's local date when it was worked out; None if never.
    """

    week_percent: float | None
    streak_weeks: int
    figure_on: date | None


class Partner(BaseModel):
    """One partner as the partners panel shows them.

    Attributes:
        partner_id: The partner's user id.
        name: Their display name, copied when the partnership began.
        since: When the partnership began (naive UTC).
        figure: Their figure; None until they have opened the app since it began.
    """
    partner_id: UUID
    name: str
    since: datetime
    #: None until they have opened the app since the partnership started.
    figure: Figure | None = None


class OpenInvite(BaseModel):
    """A partner invite link that is still live.

    Attributes:
        id: The invite's id, used to revoke it.
        created_at: When it was made (naive UTC).
        expires_at: When it stops working (naive UTC).
    """
    id: UUID
    created_at: datetime
    expires_at: datetime


class Partners(BaseModel):
    """The partners panel: the caller's own figure, their partners, and open invites.

    Attributes:
        mine: The caller's own figure, recomputed when the panel is read.
        partners: Each partner and their figure.
        invites: The caller's live invite links.
    """
    mine: Figure
    partners: list[Partner]
    invites: list[OpenInvite]


class NewInvite(BaseModel):
    """A newly made invite; the only time the token is ever returned.

    Attributes:
        id: The invite's id.
        token: The secret for the link's URL fragment; only its SHA-256 is stored.
        expires_at: When it stops working (naive UTC).
    """

    id: UUID
    token: str
    expires_at: datetime


class InviteToken(BaseModel):
    """Request body carrying an invite token from a link.

    Attributes:
        token: The token, 16-100 characters.
    """
    token: str = Field(..., min_length=16, max_length=100)


class InvitePreviewOut(BaseModel):
    """What an invite link shows before accepting.

    Attributes:
        inviter_name: The inviter's display name.
        kind: What the invite is for; "partner".
    """
    inviter_name: str
    kind: str


class AcceptResult(BaseModel):
    """The outcome of accepting an invite.

    Attributes:
        status: "accepted", "invalid" (unknown, used, revoked or expired), "own" or
            "already".
    """
    status: Literal["accepted", "invalid", "own", "already"]
