from datetime import date, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

#: Nothing a student saves toward is beyond this, and a figure past it is a
#: slipped digit rather than a plan.
MAX_TARGET = 1_000_000.0


class SinkingFundBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    target_amount: float = Field(..., gt=0, le=MAX_TARGET)
    due_on: date
    from_account_id: UUID
    to_account_id: UUID
    archived: bool = False

    @model_validator(mode="after")
    def validate_fund(self):
        if self.name.strip() == "":
            raise ValueError("A fund needs a name")
        if self.from_account_id == self.to_account_id:
            raise ValueError("Money has to move between two different accounts")
        return self


class SinkingFundCreate(SinkingFundBase):
    pass


class SinkingFundUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    target_amount: float | None = Field(default=None, gt=0, le=MAX_TARGET)
    due_on: date | None = None
    from_account_id: UUID | None = None
    to_account_id: UUID | None = None
    archived: bool | None = None


class SinkingContribution(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    for_month: date
    amount: float
    #: Null only for a contribution whose transfer has since been deleted, which
    #: the cascade normally prevents.
    group_id: UUID | None = None
    confirmed_at: datetime | None = None

    class Config:
        from_attributes = True


class SinkingFund(SinkingFundBase):
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
        from_attributes = True


class ContributionRequest(BaseModel):
    """Confirm this month's set-aside, writing the transfer."""

    #: Defaults to the derived figure, but a smaller month is allowed: putting
    #: something aside beats putting nothing aside, and the next month's figure
    #: absorbs the difference.
    amount: float | None = Field(default=None, gt=0, le=MAX_TARGET)
    occurred_on: date | None = None
