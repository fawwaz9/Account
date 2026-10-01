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


#: Seeded for a new account holder, and deliberately kept to a starting point
#: rather than a complete set. The first four come from the project notes and
#: carry the income split; School starts at 0% so adding it does not quietly
#: take a cut from the others.
#:
#: Anything more specific belongs to the person, not to this list -- accounts
#: are fully creatable in the app, so a pot for money lent out, a joint account
#: or a pot held for someone else is theirs to add with the name and kind they
#: want. A seeded account nobody asked for is clutter they have to delete.
DEFAULT_ACCOUNTS: list[tuple[str, AccountKind, float]] = [
    ("Spending", AccountKind.SPENDING, 50.0),
    ("Savings", AccountKind.SAVINGS, 20.0),
    ("Investments", AccountKind.INVESTMENT, 20.0),
    ("Emergency Savings", AccountKind.EMERGENCY, 10.0),
    ("School", AccountKind.OTHER, 0.0),
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


class InvestmentReturn(BaseModel):
    """What an investment account's holding is worth, over and above what went in.

    Null on every account that is not an investment, and on an investment nobody
    has recorded a reading for -- one nullable object rather than a handful of
    nullable numbers, so "no reading" is one state the client checks once instead
    of four fields it could check inconsistently.

    `difference_amount` is a **level**: how far above (positive) or below
    (negative) the ledger balance the holding sits, as of `as_of`. It is not a
    month's gain and a column of them must never be summed -- see
    `Finances/utils/returns.py`.
    """

    #: The reading itself. Positive is up on what you put in.
    difference_amount: float
    #: `difference_amount` over `ledger_balance`, rounded to 1dp. **None when the
    #: balance is zero or negative**, where the division is either undefined or
    #: flips the sign and would render a gain as a loss. The client shows the
    #: dollar figure and no percentage.
    return_percent: float | None = None
    #: The month this reading was taken for. Never optional, because a carried
    #: forward figure is only honest while it is dated -- undated, a reading from
    #: March reads as today's.
    as_of: date
    #: True when `as_of` is earlier than the month asked for, i.e. nothing was
    #: recorded for that month and the last known reading is standing in.
    is_carried_forward: bool = False
    #: The denominator the percentage used, sent so the client states what the
    #: gain is measured against rather than guessing at a balance of its own.
    ledger_balance: float = 0.0
    #: What was actually typed, so the form shows back the number entered. Not
    #: the basis of any arithmetic; after a later deposit this and
    #: `difference_amount + ledger_balance` deliberately disagree.
    market_value: float | None = None
    #: How much the holding moved **during** the month that was asked for:
    #: this month's level less the previous reading's. Null in three cases that
    #: all mean "not knowable", none of which is zero -- no month was asked for
    #: (the account card), the month has no reading of its own and this figure was
    #: carried forward, or this is the first reading ever taken and there is
    #: nothing to subtract from. Reporting 0 would assert the holding was flat.
    month_gain: float | None = None


class AccountMonthValueUpsert(BaseModel):
    """One month's reading, on its way in.

    Takes **exactly one of** the two. The client sends `market_value`, because
    that is the number you can read straight off a statement, and the service
    subtracts the month's ledger balance to get the level it stores. Accepting
    `difference_amount` directly costs one validator and is what lets a figure be
    set without a ledger lookup -- correcting an old month, or a restore.

    Sending both would be two answers to one question, and whichever the service
    happened to prefer would silently discard the other.
    """

    month: date
    market_value: float | None = None
    difference_amount: float | None = None

    @model_validator(mode="after")
    def exactly_one_figure(self):
        given = [self.market_value is not None, self.difference_amount is not None]
        if sum(given) != 1:
            raise ValueError(
                "Send either market_value or difference_amount, not both and not neither"
            )
        return self

    @model_validator(mode="after")
    def normalize_month(self):
        """A month is one value, or September is stored twenty-eight ways."""
        self.month = self.month.replace(day=1)
        return self


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
    #: Null unless this is an investment account with at least one reading. The
    #: latest reading overall, since the card is not scoped to a month.
    investment_return: InvestmentReturn | None = None

    class Config:
        from_attributes = True


class NetWorth(BaseModel):
    """What you have, and what you owe, as two figures rather than one total.

    `net_worth` is the sum of the balances that count, **plus** the latest
    recorded gain on each investment account, so the figure reflects what the
    holdings are worth rather than only what was paid for them. Debt needs no
    special case either way: a debt account's balance is already negative.
    `debt_total` reports the same money as a positive magnitude, because "Debt
    -1,000" reads as a double negative on screen.

    Accounts toggled out of the total are silently absent from both -- money
    someone else is holding is neither an asset nor a debt.
    """

    net_worth: float = 0.0
    debt_total: float = 0.0
    #: How much of `net_worth` is investment gain rather than money that has
    #: actually passed through the ledger. Reported separately because a headline
    #: that moves with how recently someone remembered to record a reading has to
    #: be able to say so on its face.
    investment_gain: float = 0.0


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
    #: Which pot this is. Carried so the page can tell an investment account from
    #: a spending one -- it could not before, which is why every account showed
    #: the same tiles regardless of what it was for.
    kind: AccountKind = AccountKind.SPENDING

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
    #: True when `planned` is the sum of this account's category limits rather
    #: than a figure typed into Planned spend. Sent so the client can say where
    #: the number came from instead of offering to edit something derived.
    planned_is_derived: bool = False

    #: One entry per day of the month, zero-filled, so the axis is a true
    #: calendar rather than only the days that happened to have movement.
    daily: list[DayFlow] = []
    by_category: list[CategorySpend] = []
    balance_history: list[BalancePoint] = []

    #: The investment reading that applies to the selected month -- that month's
    #: own, or the last one taken before it, flagged as carried forward. Null for
    #: every non-investment account.
    investment_return: InvestmentReturn | None = None
    #: What the ledger said at the **end of the selected month, or today if the
    #: month has not ended**. The figure the entry form subtracts a typed market
    #: value from, sent so the form shows what it is subtracting instead of
    #: reaching for `balance`, which is all-time and would be wrong for any past
    #: month.
    ledger_balance_at_month: float = 0.0
