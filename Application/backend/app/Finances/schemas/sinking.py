"""Request and response bodies for sinking funds: money set aside monthly for a cost.

A fund has a target and a due date; the monthly figure is derived on every read
from what is saved and the months left. A contribution row exists only once its
transfer is written. `sinking_service` builds these.
"""

from datetime import date, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

#: Nothing a student saves toward is beyond this, and a figure past it is a
#: slipped digit rather than a plan.
MAX_TARGET = 1_000_000.0


class SinkingFundBase(BaseModel):
    """Fields shared by a sinking fund's create body and its response.

    Attributes:
        name: What it is for, 1-120 characters and not blank.
        target_amount: What it must reach, in dollars, above 0 and at most
            1,000,000.
        due_on: When the money is needed.
        from_account_id: The account contributions are transferred from.
        to_account_id: The account they are transferred into; not the same as
            `from_account_id`.
        archived: Hidden from the default list; history kept.
    """

    name: str = Field(..., min_length=1, max_length=120)
    target_amount: float = Field(..., gt=0, le=MAX_TARGET)
    due_on: date
    from_account_id: UUID
    to_account_id: UUID
    archived: bool = False

    @model_validator(mode="after")
    def validate_fund(self):
        """Refuse a blank name, or the same account at both ends.

        Returns:
            The validated model.

        Raises:
            ValueError: If the name is blank or both accounts are the same.

        Note:
            This also runs whenever a stored fund is serialised as `SinkingFund`, so a
            row that breaks it makes its response fail.
        """
        if self.name.strip() == "":
            raise ValueError("A fund needs a name")
        if self.from_account_id == self.to_account_id:
            raise ValueError("Money has to move between two different accounts")
        return self


class SinkingFundCreate(SinkingFundBase):
    """Request body for creating a fund: the fields of `SinkingFundBase`.

    Both accounts must be the user's.
    """

    pass


class SinkingFundUpdate(BaseModel):
    """Request body for editing a fund; only the fields sent are changed.

    The per-month figure follows on the next read, since nothing about the schedule
    is stored.

    Attributes:
        name: New name, 1-120 characters.
        target_amount: New target, above 0 and at most 1,000,000.
        due_on: New due date.
        from_account_id: New source account; must be the user's.
        to_account_id: New destination account; must be the user's.
        archived: Archive or unarchive.
    """

    name: str | None = Field(default=None, min_length=1, max_length=120)
    target_amount: float | None = Field(default=None, gt=0, le=MAX_TARGET)
    due_on: date | None = None
    from_account_id: UUID | None = None
    to_account_id: UUID | None = None
    archived: bool | None = None


class SinkingContribution(BaseModel):
    """One month's money actually set aside for a fund.

    Attributes:
        id: The contribution's id.
        for_month: First day of the month it covers.
        amount: Dollars transferred.
        group_id: The transfer it wrote; None only when that transfer has since
            gone.
        confirmed_at: When it was made, naive UTC.
    """

    id: UUID = Field(default_factory=uuid4)
    for_month: date
    amount: float
    #: Null only for a contribution whose transfer has since been deleted, which
    #: the cascade normally prevents.
    group_id: UUID | None = None
    confirmed_at: datetime | None = None

    class Config:
        """Pydantic settings: allow building the model from an ORM row."""

        from_attributes = True


class SinkingFund(SinkingFundBase):
    """A fund as the API returns it: the base fields plus its derived figures.

    Attributes:
        id: The fund's id.
        created_at: When it was made, naive UTC.
        saved: Contributions made so far, summed.
        remaining: `target_amount` less `saved`, never below 0.
        months_left: Contributions left, counting this month; 0 once the due date
            has passed.
        per_month: What to set aside this month: `remaining / months_left`, or the
            whole remainder once the due date has passed.
        funded_this_month: Whether this month's contribution has been made.
        unfunded_this_month: `per_month` while this month is not yet funded and
            money remains, else 0; what safe-to-spend earmarks.
        overdue: True when the due date has passed and money is still owed.
        contributions: The contributions made, oldest month first.
    """

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime | None = None

    #: What has actually been set aside.
    saved: float = 0.0
    remaining: float = 0.0
    #: Contributions left, counting this month. Zero once the due date has
    #: passed, which is why `per_month` falls back to the whole remainder.
    months_left: int = 0
    #: What to set aside this month. Derived on every read, never stored: a
    #: stored schedule goes stale the moment a month is missed or the target
    #: moves, and the recovery from either is this same division.
    per_month: float = 0.0
    #: True once this month's contribution has been made.
    funded_this_month: bool = False
    #: What safe-to-spend subtracts: this month's contribution while it is still
    #: a promise rather than a transfer. Zero once the money has moved, because
    #: it is then sitting in a savings account that safe-to-spend already
    #: excludes -- counting it in both places would take it off twice.
    unfunded_this_month: float = 0.0
    #: True when the due date has gone and the target was never reached.
    overdue: bool = False

    contributions: list[SinkingContribution] = Field(default_factory=list)

    class Config:
        """Pydantic settings: allow building the model from an ORM row."""

        from_attributes = True


class ContributionRequest(BaseModel):
    """Request body confirming a month's set-aside, which writes the transfer.

    Attributes:
        amount: Dollars to set aside, above 0 and at most 1,000,000; defaults to
            `per_month` and is capped at what remains. A smaller month is allowed.
        occurred_on: The transfer's date, whose month is the month funded;
            defaults to today.
    """

    #: Defaults to the derived figure, but a smaller month is allowed: putting
    #: something aside beats putting nothing aside, and the next month's figure
    #: absorbs the difference.
    amount: float | None = Field(default=None, gt=0, le=MAX_TARGET)
    occurred_on: date | None = None
