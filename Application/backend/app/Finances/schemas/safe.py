from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class SpendableAccount(BaseModel):
    """One account counted toward what can be spent."""

    account_id: UUID
    name: str
    balance: float


class Commitment(BaseModel):
    """A charge the rules say is coming inside the window."""

    on_date: date
    description: str | None = None
    #: Positive. Every commitment here reduces what is safe; the sign is in the
    #: name, so a caller cannot add one by mistake.
    amount: float


class SafeToSpend(BaseModel):
    """What can be spent between now and the next time money arrives.

    Two figures, deliberately not one and deliberately not equals. `safe_now` is
    the answer: money that is actually in a spending account, less what is
    already committed. `safe_soon` adds work that has been done and confirmed
    but not yet paid for -- useful for planning across a pay gap, and never the
    headline, because a cheque can be late or short and this app already knows
    that happens.
    """

    #: Today, inclusive.
    starts_on: date
    #: The last day this figure has to cover: the day before the next pay date,
    #: or the end of the month when no job has a pay rule.
    ends_on: date
    days: int = 1
    #: True when the window ends at a real pay date rather than a fallback.
    until_payday: bool = False

    spendable: float = 0.0
    committed: float = 0.0
    #: This period's sinking-fund contributions not yet transferred. Zero until
    #: sinking funds exist; the field is here so the arithmetic on screen adds up
    #: without changing shape later.
    earmarked: float = 0.0
    safe_now: float = 0.0

    #: Confirmed work no cheque has covered yet.
    owed_to_you: float = 0.0
    safe_soon: float = 0.0

    #: Safe per remaining day, so the figure means something without arithmetic.
    #: Null when the total is negative -- a daily allowance of minus four pounds
    #: is not guidance.
    per_day: float | None = None

    accounts: list[SpendableAccount] = Field(default_factory=list)
    commitments: list[Commitment] = Field(default_factory=list)
