"""Request and response bodies for accounts, investment readings, net worth, activity.

An account is a user-defined pot of money whose balance is the sum of its ledger
rows. `account_service` and `activity_service` build these; `DEFAULT_ACCOUNTS`
seeds a new user's pots.
"""

from datetime import date
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from app.Finances.schemas.budget import CategorySpend


class AccountKind(str, Enum):
    """What an account is for, which drives a few rules beyond its styling.

    Safe-to-spend and the forecast read spending accounts only, the year plan
    counts spending, savings and emergency as liquid, a debt account's balance reads
    negative, and only an investment account takes market-value readings.
    """

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
    """Fields shared by an account's create body and its response.

    Attributes:
        name: 1-60 characters and not blank; unique per user, ignoring case.
        kind: What the account is for; defaults to spending.
        income_share: Default share of incoming money, 0-100. Shares are ratios:
            each is divided by the total of all accounts' shares.
        archived: Keeps its history but is no longer offered.
        position: Sort order, 0 or more.
        counts_toward_net_worth: Whether the account counts toward net worth and
            every other multi-account figure; any account may turn it off.
    """

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
        """Refuse a name that is only whitespace.

        Returns:
            The validated model.

        Raises:
            ValueError: If the name is blank.

        Note:
            This also runs whenever a stored account is serialised as `Account`, so a
            row that breaks it makes its response fail.
        """
        if self.name.strip() == "":
            raise ValueError("Account name cannot be empty")
        return self


class AccountCreate(AccountBase):
    """Request body for creating an account: the fields of `AccountBase`.

    A name the user already has, ignoring case, is refused.
    """

    pass


class AccountUpdate(BaseModel):
    """Request body for editing an account; only the fields sent are changed.

    Archiving, or changing the kind of, the last unarchived spending or savings
    account is refused.

    Attributes:
        name: New name, 1-60 characters; refused if another of the user's accounts
            has it, ignoring case.
        kind: New kind.
        income_share: New default share of income, 0-100.
        archived: Archive or unarchive.
        position: New sort position, 0 or more.
        counts_toward_net_worth: Count or stop counting the account.
    """

    name: str | None = Field(default=None, min_length=1, max_length=60)
    kind: AccountKind | None = None
    income_share: float | None = Field(default=None, ge=0, le=100)
    archived: bool | None = None
    position: int | None = Field(default=None, ge=0)
    counts_toward_net_worth: bool | None = None


class InvestmentReturn(BaseModel):
    """What an investment account's holding is worth over its ledger, from one reading.

    Attributes:
        difference_amount: The reading, a level: dollars above (positive) or below
            (negative) the ledger balance. Readings never sum.
        return_percent: `difference_amount` over `ledger_balance` as a percentage,
            1 dp; None when the balance is zero or negative.
        as_of: The month the reading was taken for, as its first day.
        is_carried_forward: True when the month asked for has no reading of its own
            and an earlier one stands in.
        ledger_balance: The balance the percentage divides by.
        market_value: The figure typed when the reading was recorded, for showing
            back; never used in arithmetic.
        month_gain: How far the holding moved during the month asked for; None when
            no month was asked for, the reading is carried forward, or it is the
            first reading.
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
    """Request body recording one month's reading for an investment account.

    Send exactly one figure: `market_value`, from which the service subtracts the
    month's ledger balance to get the level it stores, or `difference_amount`,
    stored as given.

    Attributes:
        month: Any day of the month; normalised to the first.
        market_value: What the holding was worth, in dollars.
        difference_amount: The level itself: dollars above or below the ledger.
    """

    month: date
    market_value: float | None = None
    difference_amount: float | None = None

    @model_validator(mode="after")
    def exactly_one_figure(self):
        """Require exactly one of `market_value` and `difference_amount`.

        Returns:
            The validated model.

        Raises:
            ValueError: If both or neither is given.
        """
        given = [self.market_value is not None, self.difference_amount is not None]
        if sum(given) != 1:
            raise ValueError(
                "Send either market_value or difference_amount, not both and not neither"
            )
        return self

    @model_validator(mode="after")
    def normalize_month(self):
        """Normalise `month` to the first day of its month.

        Returns:
            The model, with `month` moved to the first.
        """
        self.month = self.month.replace(day=1)
        return self


class Account(AccountBase):
    """An account as the API returns it: the `AccountBase` fields plus these.

    Attributes:
        id: The account's id.
        balance: Sum of its ledger rows, in dollars; negative for a debt.
        role_locked: True for the last unarchived spending or savings account,
            which cannot be deleted, archived or given another kind.
        investment_return: The latest reading overall, for an investment account
            that has one; None otherwise.
    """

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
        """Pydantic settings: allow building the model from an ORM row."""

        from_attributes = True


class NetWorth(BaseModel):
    """What the user has and owes, across counted, unarchived accounts.

    Attributes:
        net_worth: Counted balances summed, plus `investment_gain`. A debt balance
            is already negative, so it subtracts itself.
        debt_total: Counted debt accounts' balances as a positive magnitude; part
            of `net_worth`, never to be subtracted from it again.
        investment_gain: The latest reading on each counted investment account,
            summed.
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
    """One calendar day of an account's movement, split by direction.

    Attributes:
        day: The date.
        money_in: Income and incoming transfer legs, in dollars.
        money_out: Expenses and outgoing transfer legs, as a positive amount.
    """

    day: date
    money_in: float = 0.0
    money_out: float = 0.0


class BalancePoint(BaseModel):
    """The account's running balance at the end of one day it moved.

    Attributes:
        day: The date.
        balance: The balance after that day's rows, in dollars.
    """

    day: date
    balance: float


class AccountActivity(BaseModel):
    """Everything the account page shows for one month, in one response.

    Attributes:
        account_id: The account's id.
        account_name: The account's name.
        month: First day of the month shown.
        kind: The account's kind.
        balance: All-time balance, as on the account card.
        total_in: Money in during the month: income and incoming transfers.
        total_out: Money out during the month, positive: expenses and outgoing
            transfers.
        net: `total_in` less `total_out`.
        transaction_count: Ledger rows in the month.
        planned: The month's planned spending: the sum of the account's category
            limits when it has any, otherwise its hand-set target.
        remaining: `planned` less `total_out`.
        used_percent: `total_out / planned * 100`, 1 dp; 0 when nothing is planned.
        planned_is_derived: True when `planned` comes from category limits.
        daily: One entry per day of the month, zero-filled.
        by_category: The month's expenses by category with this account's limits;
            a limited category appears even with nothing spent.
        balance_history: The running balance after each day the account moved,
            from its first row.
        investment_return: The reading that applies to the month (its own, or the
            last one before it); None for other kinds.
        all_time_return: The latest reading against the all-time balance, as on the
            account card; None for other kinds.
        ledger_balance_at_month: The ledger at the month's end, or today for the
            current month, which a typed market value is measured against; 0 for
            other kinds.
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
    #: The latest reading overall, measured against the **all-time** balance --
    #: the same figure the account card shows.
    #:
    #: Separate from `investment_return` above because the two answer different
    #: questions and must not be mixed. The header on this page is an all-time
    #: figure, so deriving it from the month-scoped reading would add March's gain
    #: to today's balance whenever someone browsed back to March.
    all_time_return: InvestmentReturn | None = None
    #: What the ledger said at the **end of the selected month, or today if the
    #: month has not ended**. The figure the entry form subtracts a typed market
    #: value from, sent so the form shows what it is subtracting instead of
    #: reaching for `balance`, which is all-time and would be wrong for any past
    #: month.
    ledger_balance_at_month: float = 0.0
