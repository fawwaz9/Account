from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class DepositAllocation(BaseModel):
    account_id: UUID
    amount: float = Field(..., ge=0)


class DepositCreate(BaseModel):
    """Money coming in, spread across the accounts.

    With no allocations the server splits by each account's income_share.
    Supplying them overrides that for this one deposit, which is the whole
    point of having a default rather than a rule.
    """

    amount: float = Field(..., gt=0)
    occurred_on: date
    description: str | None = Field(default=None, max_length=200)
    allocations: list[DepositAllocation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_allocations(self):
        if not self.allocations:
            return self

        total = round(sum(entry.amount for entry in self.allocations), 2)
        if abs(total - round(self.amount, 2)) > 0.01:
            raise ValueError(
                f"Allocations total {total:.2f} but the deposit is {self.amount:.2f}"
            )

        seen = {entry.account_id for entry in self.allocations}
        if len(seen) != len(self.allocations):
            raise ValueError("Each account can appear only once in a deposit")

        return self


class DepositPreview(BaseModel):
    amount: float
    allocations: list[DepositAllocation] = Field(default_factory=list)
    #: True when no account carries an income share, so nothing can be split.
    needs_shares: bool = False
