"""Request and response bodies for term blackouts, the breaks when no class runs.

A blackout is a date range (a reading break, a stat holiday) that cancels every
occurrence of the user's course-linked events inside it. `blackout_service`
reads and writes them.
"""

from datetime import date
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class TermBlackoutBase(BaseModel):
    """Fields shared by a blackout's create body and its response.

    Attributes:
        label: What the break is called, 1-80 characters; the service strips it.
        starts_on: First date with no classes.
        ends_on: Last date with no classes, inclusive; equal to `starts_on` for a
            single day.
    """

    label: str = Field(..., min_length=1, max_length=80)
    starts_on: date
    #: Inclusive. Equal to starts_on for a single day, so a stat holiday and a
    #: reading break are the same shape.
    ends_on: date

    @model_validator(mode="after")
    def validate_range(self):
        """Reject a range that ends before it starts.

        Returns:
            The validated model.

        Raises:
            ValueError: If `ends_on` is before `starts_on`.
        """
        if self.ends_on < self.starts_on:
            raise ValueError("A blocked period ends before it starts")
        return self


class TermBlackoutCreate(TermBlackoutBase):
    """Request body for adding a blackout: the fields of `TermBlackoutBase`.

    The service also refuses a range longer than 120 days.
    """

    pass


class TermBlackoutUpdate(BaseModel):
    """Request body for editing a blackout; omitted or null fields keep their value.

    The service checks the merged range, since either end may move on its own.

    Attributes:
        label: New name, 1-80 characters.
        starts_on: New first date.
        ends_on: New last date, inclusive.
    """

    label: str | None = Field(default=None, min_length=1, max_length=80)
    starts_on: date | None = None
    ends_on: date | None = None


class TermBlackout(TermBlackoutBase):
    """A blackout as the API returns it: the `TermBlackoutBase` fields plus these.

    Attributes:
        id: The blackout's id.
        days: How many dates the range covers, counting both ends.
    """

    id: UUID = Field(default_factory=uuid4)
    #: How many dates the range covers, so the client can say "5 days" without
    #: doing calendar arithmetic.
    days: int = 1

    class Config:
        """Pydantic settings: allow building the model from an ORM row."""

        from_attributes = True
