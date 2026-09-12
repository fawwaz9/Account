"""Stretches of term when classes do not run."""

from datetime import date
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class TermBlackoutBase(BaseModel):
    label: str = Field(..., min_length=1, max_length=80)
    starts_on: date
    #: Inclusive. Equal to starts_on for a single day, so a stat holiday and a
    #: reading break are the same shape.
    ends_on: date

    @model_validator(mode="after")
    def validate_range(self):
        if self.ends_on < self.starts_on:
            raise ValueError("A blocked period ends before it starts")
        return self


class TermBlackoutCreate(TermBlackoutBase):
    pass


class TermBlackoutUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=80)
    starts_on: date | None = None
    ends_on: date | None = None


class TermBlackout(TermBlackoutBase):
    id: UUID = Field(default_factory=uuid4)
    #: How many dates the range covers, so the client can say "5 days" without
    #: doing calendar arithmetic.
    days: int = 1

    class Config:
        from_attributes = True
