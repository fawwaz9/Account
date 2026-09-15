from datetime import date
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from app.Finances.schemas.budget import CategorySpend


class AccountKind(str, Enum):
    SPENDING = "spending"
    SAVINGS = "savings"
    INVESTMENT = "investment"
    EMERGENCY = "emergency"
    OTHER = "other"
    #: Money owed rather than held -- a credit card, a student loan. Its balance
    #: is the ordinary signed sum of its rows, so it reads negative: buying with
    #: the card is an expense on the account, and paying it down is an ordinary
    #: transfer that moves it toward zero. Nothing has to special-case the sign,
    #: and a total that adds every balance subtracts debt for free.
    DEBT = "debt"


#: Kinds the app depends on having at least one of. Losing the last spending
#: account takes safe-to-spend's only source away; losing the last savings
#: account leaves nowhere for the income split to land.
PROTECTED_KINDS: frozenset[AccountKind] = frozenset(
    {AccountKind.SPENDING, AccountKind.SAVINGS}
)


#: Seeded for a new account holder. The first four come from the project notes
#: and carry the income split; School and Money Lent start at 0% so adding them
#: does not quietly take a cut from the others.
DEFAULT_ACCOUNTS: list[tuple[str, AccountKind, float]] = [
    ("Spending", AccountKind.SPENDING, 50.0),
    ("Savings", AccountKind.SAVINGS, 20.0),
    ("Investments", AccountKind.INVESTMENT, 20.0),
    ("Emergency Savings", AccountKind.EMERGENCY, 10.0),
    ("School", AccountKind.OTHER, 0.0),
    ("Money Lent", AccountKind.OTHER, 0.0),
]


class AccountBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    kind: AccountKind = Field(default=AccountKind.SPENDING)
    income_share: float = Field(default=0.0, ge=0, le=100, description="Default share of income, percent")
    archived: bool = Field(default=False)
    position: int = Field(default=0, ge=0)
    counts_toward_net_worth: bool = Field(
        default=True,
        description="Whether this balance reaches net worth. Any account may turn it off.",
    )

    @model_validator(mode="after")
    def validate_account(self):
        if self.name.strip() == "":
            raise ValueError("Account name cannot be empty")
        return self


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    kind: AccountKind | None = None
    income_share: float | None = Field(default=None, ge=0, le=100)
    archived: bool | None = None
    position: int | None = Field(default=None, ge=0)
    counts_toward_net_worth: bool | None = None


class Account(AccountBase):
    id: UUID = Field(default_factory=uuid4)
    #: Sum of the account's transactions. Derived rather than stored: a balance
    #: that disagrees with its own ledger is worse than one that costs a query.
    balance: float = 0.0
    #: The last non-archived account of a kind the app depends on, so deleting,
    #: archiving or re-kinding it is refused. Attached by the service so the
    #: rule has one home; the client greys out the controls rather than
    #: deciding for itself which accounts are load-bearing.
    role_locked: bool = False

    class Config:
        from_attributes = True


class NetWorth(BaseModel):
    """What you have, and what you owe, as two figures rather than one total.

    `net_worth` is a plain sum of the balances that count, which is why debt
    needs no special case: a debt account's balance is already negative.
    `debt_total` reports the same money as a positive magnitude, because "Debt
    -1,000" reads as a double negative on screen.

    Accounts toggled out of the total are silently absent from both -- money
    someone else is holding is neither an asset nor a debt.
    """

    net_worth: float = 0.0
    debt_total: float = 0.0


# ------------------------------------------------------------------ activity --

class DayFlow(BaseModel):
    """One calendar day of an account's movement, split by direction."""

    day: date
    money_in: float = 0.0
    money_out: float = 0.0


class BalancePoint(BaseModel):
    """The account's running balance as of the end of a day that had activity.

    One point per active date rather than per calendar day: the line is a step
    function either way, and a quiet year should not cost 365 points.
    """

    day: date
    balance: float


class AccountActivity(BaseModel):
    """Everything the account page shows, for one month, in one response.

    Composed server-side for the same reason the deposit preview is: the
    direction rule that decides what counts as money out lives in one place,
    and a chart assembled from a capped page of rows would quietly lose the
    oldest ones.
    """

    account_id: UUID
    account_name: str
    month: date

    #: All-time, matching what the account card shows.
    balance: float = 0.0

    #: The selected month only.
    total_in: float = 0.0
    total_out: float = 0.0
    net: float = 0.0
    transaction_count: int = 0

    #: This account's target for the selected month.
    planned: float = 0.0
    remaining: float = 0.0
    used_percent: float = 0.0

    #: One entry per day of the month, zero-filled, so the axis is a true
    #: calendar rather than only the days that happened to have movement.
    daily: list[DayFlow] = []
    by_category: list[CategorySpend] = []
    balance_history: list[BalancePoint] = []
