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


class SubscriptionOccurrence(BaseModel):
    """One charge that went into a subscription's pattern."""

    transaction_id: UUID
    on_date: date
    amount: float


class SubscriptionCandidate(BaseModel):
    """A run of expenses that looks like a subscription, but is not one yet.

    Nothing here is stored. It is derived fresh from the ledger every time, so
    there is nothing to keep in sync when a description changes or a charge is
    corrected -- the pattern is just read again.
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
    """Turn a finding into a standing instruction, and stop re-finding it.

    `transaction_ids` are the charges that made up the pattern -- exactly
    `SubscriptionCandidate.occurrences`, echoed back rather than re-derived, so
    confirming a stale card can never tag the wrong rows. Without tagging them,
    the same history would still have no `recurring_id` and would qualify as a
    pattern again on the very next read.
    """

    transaction_ids: list[UUID]
    instruction: RecurringCreate
