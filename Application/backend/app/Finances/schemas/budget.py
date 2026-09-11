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

    @model_validator(mode="after")
    def validate_category(self):
        if self.name.strip() == "":
            raise ValueError("Category name cannot be empty")
        return self


class SpendCategoryCreate(SpendCategoryBase):
    pass


class SpendCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    archived: bool | None = None
    position: int | None = Field(default=None, ge=0)


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
    #: Expenses only. A transfer moves money rather than spending it, so it
    #: does not count against a spending target.
    actual: float = 0.0
    remaining: float = 0.0
    #: Share of the plan used, 0-100+. 0 when nothing is planned.
    used_percent: float = 0.0


class CategorySpend(BaseModel):
    category_id: UUID | None = None
    category_name: str
    actual: float = 0.0


class BudgetSummary(BaseModel):
    month: date
    total_planned: float = 0.0
    total_actual: float = 0.0
    accounts: list[AccountBudget] = Field(default_factory=list)
    by_category: list[CategorySpend] = Field(default_factory=list)
