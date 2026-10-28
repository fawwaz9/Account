"""Request and response bodies for categories, targets, category limits and budgets.

`budget_service` reads and writes spending categories, monthly targets and
per-account category limits, and builds the monthly summary; `tuition_service`
builds the term budget.
"""

from datetime import date
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


def first_of_month(value: date) -> date:
    """Return the first day of the month a date falls in.

    Args:
        value: Any day of the month.

    Returns:
        That month's first day, the one form a month is stored in.
    """
    return value.replace(day=1)


class SpendCategoryBase(BaseModel):
    """Fields shared by a spending category's create body and its response.

    Attributes:
        name: 1-60 characters and not blank; unique per user, ignoring case.
        archived: Hidden from pickers; past expenses keep the category.
        position: Sort order, 0 or more.
    """

    name: str = Field(..., min_length=1, max_length=60)
    archived: bool = Field(default=False)
    position: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_category(self):
        """Refuse a name that is only whitespace.

        Returns:
            The validated model.

        Raises:
            ValueError: If the name is blank.
        """
        if self.name.strip() == "":
            raise ValueError("Category name cannot be empty")
        return self


class SpendCategoryCreate(SpendCategoryBase):
    """Request body for creating a category: the fields of `SpendCategoryBase`."""

    pass


class SpendCategoryUpdate(BaseModel):
    """Request body for renaming, archiving or reordering a category.

    Only the fields sent are changed.

    Attributes:
        name: New name, 1-60 characters; refused if another of the user's
            categories has it, ignoring case.
        archived: Archive or unarchive.
        position: New sort position, 0 or more.
    """

    name: str | None = Field(default=None, min_length=1, max_length=60)
    archived: bool | None = None
    position: int | None = Field(default=None, ge=0)


class SpendCategory(SpendCategoryBase):
    """A spending category as the API returns it: the base fields plus its id.

    Attributes:
        id: The category's id.
    """

    id: UUID = Field(default_factory=uuid4)

    class Config:
        """Pydantic settings: allow building the model from an ORM row."""

        from_attributes = True


class BudgetTargetUpsert(BaseModel):
    """Request body setting one account's planned spending for one month.

    Creates the month's target or replaces it.

    Attributes:
        account_id: The account; must be one of the user's.
        month: Any day of the month; normalised to the first.
        planned_amount: Dollars planned, 0 or more.
    """

    account_id: UUID
    month: date
    planned_amount: float = Field(..., ge=0)

    @field_validator("month")
    @classmethod
    def normalize_month(cls, value: date) -> date:
        """Normalise the month to its first day.

        Args:
            value: Any day of the month.

        Returns:
            The month's first day.
        """
        return first_of_month(value)


class AccountBudget(BaseModel):
    """One account's month: what was planned against what went out.

    Attributes:
        account_id: The account's id.
        account_name: The account's name.
        planned: Planned spending in dollars: the sum of the account's category
            limits when it has any, otherwise its hand-set target (0 without one).
        actual: Money out in the month, in dollars and positive: expenses plus the
            outgoing leg of transfers.
        remaining: `planned` less `actual`; negative when over.
        used_percent: `actual / planned * 100`, 1 dp and not clamped; 0 when
            nothing is planned.
        planned_is_derived: True when `planned` is the sum of category limits, so
            the client shows it without an edit control.
    """

    account_id: UUID
    account_name: str
    planned: float = 0.0
    #: Expenses plus the outgoing leg of transfers: money moved out of the
    #: account counts against its target; the incoming leg does not.
    actual: float = 0.0
    remaining: float = 0.0
    #: Share of the plan used, 0-100+. 0 when nothing is planned.
    used_percent: float = 0.0
    #: True when `planned` is the sum of this account's category limits. The
    #: budget page shows such a figure without offering to edit it -- one number
    #: with two places to set it is the shape where the last edit quietly wins.
    planned_is_derived: bool = False


class CategorySpend(BaseModel):
    """One category's spending over a period.

    `limit` and the fields derived from it are set only on an account's own page,
    where the limit and the spending cover the same money. The budget summary spans
    every account and leaves them at their defaults.

    Attributes:
        category_id: The category; None for uncategorised spending, and on every
            row of the term budget, which groups by name.
        category_name: The category's name, or "Uncategorised".
        actual: Spent in the period, in dollars and positive.
        limit: The account's limit for the month; None means no limit, while 0
            means nothing should be spent there.
        remaining: `limit` less `actual`, negative when over; 0 without a limit.
        used_percent: `actual / limit * 100`, 1 dp and not clamped; 0 when there
            is no limit or the limit is 0.
        limit_is_override: True when the month's limit is an override of the
            standing one.
    """

    category_id: UUID | None = None
    category_name: str
    actual: float = 0.0
    #: What this account means to spend here. None is "no limit"; 0 is "nothing
    #: is meant to go here", under which any spending is over.
    limit: float | None = None
    #: limit - actual. Negative is overspent. 0.0 when there is no limit.
    remaining: float = 0.0
    #: Share of the limit used, 0-100+, not clamped -- the client needs to see it
    #: pass 100 to colour the bar. 0.0 when there is no limit.
    used_percent: float = 0.0
    #: True when this month differs from the account's standing limit for the
    #: category, so the UI can say why the figure is not the usual one.
    limit_is_override: bool = False


class AccountCategoryLimitUpsert(BaseModel):
    """Request body setting or clearing what one account may spend on one category.

    A null `limit_amount` deletes the row, so the category has no limit on that
    account; when it was the last one, the account falls back to its hand-set target.

    Attributes:
        account_id: The account; must be one of the user's.
        category_id: The category; must be one of the user's.
        month: None sets the standing limit for every month; a date (normalised to
            the first) sets that month's override and leaves the standing one alone.
        limit_amount: The monthly ceiling in dollars, 0 or more; null removes it.
    """

    account_id: UUID
    category_id: UUID
    #: None sets the **standing** limit, which applies to every month. A date
    #: sets that month's override instead, leaving the standing figure alone.
    month: date | None = None
    limit_amount: float | None = Field(default=None, ge=0)

    @field_validator("month")
    @classmethod
    def normalize_month(cls, value: date | None) -> date | None:
        """Normalise the month to its first day, leaving None alone.

        Args:
            value: Any day of the month, or None for the standing limit.

        Returns:
            The month's first day, or None.
        """
        return first_of_month(value) if value is not None else None


class BudgetSummary(BaseModel):
    """Response body for one month across every counted, unarchived account.

    Attributes:
        month: The month's first day.
        total_planned: The accounts' planned figures, summed.
        total_actual: The accounts' actual figures, summed.
        accounts: One entry per counted, unarchived account, in the user's order.
        by_category: Expenses per category on counted accounts, largest first,
            with no limits attached.
    """

    month: date
    total_planned: float = 0.0
    total_actual: float = 0.0
    accounts: list[AccountBudget] = Field(default_factory=list)
    by_category: list[CategorySpend] = Field(default_factory=list)


class TermBudget(BaseModel):
    """What the current term has cost, measured over the term's own dates.

    Attributes:
        term_name: The term as a person would write it.
        starts_on: First day of the term; None when it has no dates (no first-year
            anchor set, or no courses in the current term).
        ends_on: Last day of the term; None likewise.
        dated_courses: Current-term courses with their own start and end dates.
        undated_courses: Current-term courses without them.
        spent: Expenses in the term on counted accounts, in dollars and positive.
        received: Income in the term on counted accounts.
        net: `received` less `spent`.
        on_courses: Expenses tagged to one of the term's courses. Tuition payments
            carry no course, so they are not included.
        by_category: Expenses by category name, largest first.
        days_elapsed: Days of the term so far, between 0 and `days_total`.
        days_total: Length of the term in days.
        can_measure: Whether the term has dates to measure over.
        reason: Why it cannot be measured, when it cannot.
    """

    term_name: str = "your current term"
    #: None when the term cannot be dated (no first-year anchor, or no courses in
    #: it), in which case there is no span to measure and `reason` says so.
    starts_on: date | None = None
    ends_on: date | None = None
    #: Courses with their own start and end dates; the span itself comes from
    #: the term's fixed dates, not from these.
    dated_courses: int = 0
    undated_courses: int = 0
    spent: float = 0.0
    received: float = 0.0
    net: float = 0.0
    #: Spend on anything tagged to a course in this term. Tuition payments carry
    #: no course, so they are not included.
    on_courses: float = 0.0
    by_category: list[CategorySpend] = Field(default_factory=list)
    days_elapsed: int = 0
    days_total: int = 0
    can_measure: bool = False
    reason: str | None = None
