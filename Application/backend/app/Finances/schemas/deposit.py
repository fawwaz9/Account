"""Request and response bodies for a deposit: income split across accounts.

A deposit is one income row per receiving account, tied by a shared `group_id`.
`deposit_service` previews and records it, splitting by income share unless the
caller gives the amounts.
"""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class DepositAllocation(BaseModel):
    """One account's part of a deposit.

    Attributes:
        account_id: The receiving account; one of the user's unarchived accounts.
        amount: Dollars it receives, 0 or more; 0 writes no row.
    """

    account_id: UUID
    amount: float = Field(..., ge=0)


class DepositCreate(BaseModel):
    """Request body for recording incoming money split across accounts.

    With no allocations the server splits by each account's income share, putting
    the rounding remainder on the largest share; allocations override that for
    this one deposit.

    Attributes:
        amount: The total received, in dollars, above 0.
        occurred_on: The day it arrived.
        description: Up to 200 characters; "Deposit" when omitted.
        allocations: Explicit amounts per account, each account once; they must
            total `amount` to the cent.
    """

    amount: float = Field(..., gt=0)
    occurred_on: date
    description: str | None = Field(default=None, max_length=200)
    allocations: list[DepositAllocation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_allocations(self):
        """Check that allocations total the deposit exactly and name each account once.

        Returns:
            The validated model.

        Raises:
            ValueError: If the allocations' total differs from `amount` by a cent or
                more, or an account appears twice.
        """
        if not self.allocations:
            return self

        # Compared as whole cents, and required to match exactly. A tolerance of
        # `> 0.01` let allocations of 100.01 through against a deposit of
        # 100.00 -- the split has to account for the money that arrived and not
        # a cent more, and integers are also what keeps float fuzz out of the
        # comparison without needing a tolerance to absorb it.
        total = round(sum(entry.amount for entry in self.allocations), 2)
        if round(total * 100) != round(self.amount * 100):
            raise ValueError(
                f"Allocations total {total:.2f} but the deposit is {self.amount:.2f}"
            )

        seen = {entry.account_id for entry in self.allocations}
        if len(seen) != len(self.allocations):
            raise ValueError("Each account can appear only once in a deposit")

        return self


class DepositPreview(BaseModel):
    """How a deposit would split by income share, before anything is written.

    Attributes:
        amount: The deposit, rounded to cents.
        allocations: Each sharing account's amount, summing to `amount`; empty when
            no account has a share.
        needs_shares: True when no unarchived account carries an income share, so
            nothing can be split.
    """

    amount: float
    allocations: list[DepositAllocation] = Field(default_factory=list)
    #: True when no account carries an income share, so nothing can be split.
    needs_shares: bool = False
