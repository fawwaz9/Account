"""Request and response bodies for the subscription audit: undeclared repeating charges.

`subscription_service` derives candidates fresh from the ledger on every call;
confirming one creates a standing instruction and tags the charges that made the
case, so the same run is not found again.
"""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.Finances.schemas.recurring import RecurringCreate

#: The three cadences this looks for, in days between charges. A charge that
#: lands outside every window -- a irregular top-up, a one-off refund that
#: repeated by coincidence twice -- is not a subscription and is left alone.
CADENCE_GAP_DAYS: dict[str, tuple[int, int]] = {
    "weekly": (6, 8),
    "fortnightly": (13, 16),
    "monthly": (25, 35),
}

#: How many times a charge must repeat, and how tightly the amounts must agree,
#: before it is worth showing. Both live here rather than in the function body
#: so they can be tuned without reading the matching logic.
MIN_OCCURRENCES = 3
AMOUNT_TOLERANCE = 0.10
"""Largest fraction a charge may stray from the run's median amount (0.10 is 10%)."""


class SubscriptionOccurrence(BaseModel):
    """One charge that is part of a subscription's pattern.

    Attributes:
        transaction_id: The ledger row.
        on_date: When it was charged.
        amount: What it charged, as a positive figure.
    """

    transaction_id: UUID
    on_date: date
    amount: float


class SubscriptionCandidate(BaseModel):
    """A run of expenses that looks like a subscription but has no standing instruction.

    Never stored: it is read again from the ledger each time, so a corrected charge
    or description simply changes the next answer.

    Attributes:
        description: The most recent charge's own text.
        account_id: The account the most recent charge came from.
        category_id: The most recent charge's category.
        cadence: "weekly", "fortnightly" or "monthly", the rhythm every gap fits.
        median_amount: The median charge, in dollars.
        first_seen: Date of the first charge in the run.
        last_seen: Date of the latest charge.
        next_expected_on: Where the next charge should land, and where `suggested`
            starts.
        occurrences: The charges in the run, oldest first.
        suggested: A standing instruction ready to submit as it is.
    """

    #: The most recent charge's own text, so what is shown matches the ledger.
    description: str
    account_id: UUID
    category_id: UUID | None = None
    cadence: Literal["weekly", "fortnightly", "monthly"]
    median_amount: float
    first_seen: date
    last_seen: date
    #: Where the pattern says the next one lands, and where `suggested` starts.
    next_expected_on: date
    occurrences: list[SubscriptionOccurrence] = Field(default_factory=list)
    #: Ready to submit as-is. Turning a finding into a standing instruction is
    #: what makes this actionable rather than trivia -- the whole point of
    #: detecting a pattern nobody named as recurring.
    suggested: RecurringCreate


class SubscriptionConfirm(BaseModel):
    """Request body turning a finding into a standing instruction.

    Attributes:
        transaction_ids: The finding's occurrences, echoed back from the card
            rather than re-derived; each is tagged with the new instruction so the
            run stops qualifying.
        instruction: The standing instruction to create, usually `suggested` with
            any edits.
    """

    transaction_ids: list[UUID]
    instruction: RecurringCreate
