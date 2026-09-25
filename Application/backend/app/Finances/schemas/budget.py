from datetime import date
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


def first_of_month(value: date) -> date:
    """Normalize any day in a month to the first.

    A month has to be one value, or "September" ends up stored twenty-eight
    different ways and no two targets ever match.
    """
    return value.replace(day=1)


class SpendCategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    archived: bool = Field(default=False)
    position: int = Field(default=0, ge=0)
    #: What you mean to spend here each month. None is "no limit"; 0 is "nothing
    #: is meant to go here", under which any spending is over. The two must stay
    #: separable -- see app/Finances/utils/limits.py.
    monthly_limit: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_category(self):
        if self.name.strip() == "":
            raise ValueError("Category name cannot be empty")
        return self


class SpendCategoryCreate(SpendCategoryBase):
    pass


class SpendCategoryUpdate(BaseModel):
    """A patch: every field optional, and absence means "leave it alone".

    `monthly_limit` is the one field where that convention is not enough, because
    None is also a value someone means -- "remove the limit". The two are told
    apart by whether the key was *sent*, which `model_dump(exclude_unset=True)`
    reports and a default cannot. Without that, a limit could be set and never
    removed.
    """

    name: str | None = Field(default=None, min_length=1, max_length=60)
    archived: bool | None = None
    position: int | None = Field(default=None, ge=0)
    monthly_limit: float | None = Field(default=None, ge=0)


class SpendCategory(SpendCategoryBase):
    id: UUID = Field(default_factory=uuid4)

    class Config:
        from_attributes = True


class BudgetTargetUpsert(BaseModel):
    account_id: UUID
    month: date
    planned_amount: float = Field(..., ge=0)

    @field_validator("month")
    @classmethod
    def normalize_month(cls, value: date) -> date:
        return first_of_month(value)


class AccountBudget(BaseModel):
    """One account's month: what was planned, what actually went out."""

    account_id: UUID
    account_name: str
    planned: float = 0.0
    #: Expenses **plus the outgoing half of a transfer**: money moved out of a
    #: pot has left it as surely as money spent from it. Only the negative leg
    #: counts; the matching positive one lands on the receiving account.
    #:
    #: This said "expenses only -- a transfer moves money rather than spending
    #: it", which is the opposite of what budget_service does. The frontend's
    #: copy of the comment was corrected and this one was missed, so the trap
    #: stayed where the code is.
    actual: float = 0.0
    remaining: float = 0.0
    #: Share of the plan used, 0-100+. 0 when nothing is planned.
    used_percent: float = 0.0


class CategorySpend(BaseModel):
    """One category's month, mirroring AccountBudget so both panels render alike.

    `limit` is None for a category with no limit, for Uncategorised (which can
    never have one, having no row to hang it on), and for every row the account
    detail page asks for -- a limit spans every account, so judging one against
    a single account's share of the spending would be a different, wrong figure.
    A None limit means the client draws no bar, rather than drawing an empty one.
    """

    category_id: UUID | None = None
    category_name: str
    actual: float = 0.0
    #: The limit in force this month: the month's override, else the standing
    #: one. None when neither exists.
    limit: float | None = None
    #: limit - actual. Negative is overspent. 0.0 when there is no limit.
    remaining: float = 0.0
    #: Share of the limit used, 0-100+. 0 when there is no limit. Computed here
    #: rather than in the client because ProgressBar rounds it to 1dp and the
    #: two answers disagree at the "close" boundary.
    used_percent: float = 0.0
    #: True when this month differs from the category's standing limit, so the
    #: UI can say why the figure is not the usual one.
    limit_is_override: bool = False


class CategoryLimitUpsert(BaseModel):
    """Set or clear one category's limit for one month.

    `limit_amount` of None **deletes the override**, so the month falls back to
    the category's standing limit. That is why this is a PUT: the month's
    override is replaced whole, including with nothing.
    """

    category_id: UUID
    month: date
    limit_amount: float | None = Field(default=None, ge=0)

    @field_validator("month")
    @classmethod
    def normalize_month(cls, value: date) -> date:
        return first_of_month(value)


class BudgetSummary(BaseModel):
    month: date
    total_planned: float = 0.0
    total_actual: float = 0.0
    accounts: list[AccountBudget] = Field(default_factory=list)
    by_category: list[CategorySpend] = Field(default_factory=list)


class TermBudget(BaseModel):
    """What a term cost, measured over the term rather than a calendar month.

    A month is the wrong unit for a student. Tuition lands once, textbooks land
    in the first fortnight, and the question worth asking is what the *term* has
    taken -- which Grades already knows the shape of, because its courses carry
    their own start and end dates.
    """

    term_name: str = "your current term"
    #: None when no course in the term carries dates, in which case there is no
    #: span to measure and `reason` says so rather than inventing one.
    starts_on: date | None = None
    ends_on: date | None = None
    #: Courses that supplied the span, so it is obvious where it came from.
    dated_courses: int = 0
    undated_courses: int = 0
    spent: float = 0.0
    received: float = 0.0
    net: float = 0.0
    #: Spend on anything tagged to a course in this term, tuition included.
    on_courses: float = 0.0
    by_category: list[CategorySpend] = Field(default_factory=list)
    days_elapsed: int = 0
    days_total: int = 0
    can_measure: bool = False
    reason: str | None = None
