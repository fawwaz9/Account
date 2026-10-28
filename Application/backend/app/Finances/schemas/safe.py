"""Response bodies for safe-to-spend: what can be spent before money next arrives.

`safe_service` computes it from the counted spending accounts' balances, the
standing instructions due in the window, and sinking-fund contributions not yet
made.
"""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class SpendableAccount(BaseModel):
    """One account counted toward what can be spent.

    Attributes:
        account_id: The account's id.
        name: The account's name.
        balance: Its ledger balance in dollars, signed.
    """

    account_id: UUID
    name: str
    balance: float


class Commitment(BaseModel):
    """A standing charge due inside the window, taken off what is safe.

    Attributes:
        on_date: When it is due.
        description: The standing instruction's description.
        amount: What it takes, as a positive figure.
    """

    on_date: date
    description: str | None = None
    #: Positive. Every commitment here reduces what is safe; the sign is in the
    #: name, so a caller cannot add one by mistake.
    amount: float


class SafeToSpend(BaseModel):
    """What can be spent between today and the day before money next arrives.

    `safe_now` is the headline: cash in the spending accounts less what is already
    committed. `safe_soon` adds hourly work done but not yet paid for and is never
    the headline, because a cheque can be late or short.

    Attributes:
        starts_on: Today, on the user's clock.
        ends_on: The day before the soonest pay date of any current job, or the
            month's end when no job has one.
        days: Days in the window, today included; at least 1.
        until_payday: True when the window ends at a real pay date.
        spendable: The counted, unarchived spending accounts' balances, summed.
        committed: Outgoing standing instructions (expenses and transfers) due in
            the window from any counted account, summed.
        earmarked: This month's sinking-fund contributions not yet transferred,
            from funds paid by counted accounts.
        safe_now: `spendable` less `committed` and `earmarked`; may be negative.
        owed_to_you: Estimated pay for hourly shifts no cheque has covered yet.
        safe_soon: `safe_now` plus `owed_to_you`.
        per_day: `safe_now` divided by `days`; None when `safe_now` is zero or
            negative.
        accounts: The spending accounts counted.
        commitments: The charges behind `committed`, by date.
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
