from datetime import date
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from app.Finances.schemas.deposit import DepositAllocation

#: Nothing one cheque pays is beyond this, and a figure past it is a slipped
#: digit rather than a wage.
MAX_CHEQUE = 1_000_000.0


class DeductionEntry(BaseModel):
    """Something taken off a cheque before it arrived.

    Income tax, EI, CPP, union dues -- money that was earned and never reached
    the account. Recording it as income would invent a deposit that never
    happened; leaving it out would make the gross unexplainable.
    """

    description: str = Field(..., min_length=1, max_length=120)
    #: Positive. The sign is in the name.
    amount: float = Field(..., gt=0, le=MAX_CHEQUE)


class PaychequeBase(BaseModel):
    job_id: UUID
    occurred_on: date
    gross_amount: float = Field(..., gt=0, le=MAX_CHEQUE)
    #: The stretch of work this cheque was for. Both or neither.
    period_start: date | None = None
    period_end: date | None = None
    deductions: list[DeductionEntry] = Field(default_factory=list, max_length=20)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_paycheque(self):
        if (self.period_start is None) != (self.period_end is None):
            raise ValueError("Give both ends of the pay period, or neither")
        if (
            self.period_start is not None
            and self.period_end is not None
            and self.period_end < self.period_start
        ):
            raise ValueError("A pay period cannot end before it starts")

        total = round(sum(entry.amount for entry in self.deductions), 2)
        if total >= round(self.gross_amount, 2):
            raise ValueError(
                f"Deductions total {total:.2f}, which is not less than the "
                f"gross of {self.gross_amount:.2f}"
            )

        return self


class PaychequeCreate(PaychequeBase):
    """What arrived, and where the net should land.

    With no allocations the net splits by each account's income share, exactly
    as any other deposit does. Supplying them overrides that for this cheque.
    """

    allocations: list[DepositAllocation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_allocations(self):
        if not self.allocations:
            return self

        net = round(self.gross_amount - sum(e.amount for e in self.deductions), 2)
        total = round(sum(entry.amount for entry in self.allocations), 2)
        if abs(total - net) > 0.01:
            raise ValueError(
                f"Allocations total {total:.2f} but the net is {net:.2f}"
            )

        seen = {entry.account_id for entry in self.allocations}
        if len(seen) != len(self.allocations):
            raise ValueError("Each account can appear only once on a cheque")

        return self


class PaychequeUpdate(BaseModel):
    """A correction. The whole cheque is rewritten, ledger rows included.

    Every field is optional, but `deductions` replaces the list wholesale rather
    than merging: a deduction removed from the form has to be removed from the
    cheque, and there is no stable id to match a partial list against.
    """

    occurred_on: date | None = None
    gross_amount: float | None = Field(default=None, gt=0, le=MAX_CHEQUE)
    period_start: date | None = None
    period_end: date | None = None
    deductions: list[DeductionEntry] | None = Field(default=None, max_length=20)
    allocations: list[DepositAllocation] | None = None
    notes: str | None = Field(default=None, max_length=2000)


class Deduction(DeductionEntry):
    id: UUID = Field(default_factory=uuid4)

    class Config:
        from_attributes = True


class Paycheque(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    job_id: UUID
    job_name: str
    occurred_on: date
    gross_amount: float
    deductions: list[Deduction] = Field(default_factory=list)
    #: Gross less every deduction. Computed rather than stored: it is a
    #: subtraction, and storing it would let the two disagree.
    net_amount: float = 0.0
    period_start: date | None = None
    period_end: date | None = None
    #: What the hours in the period said it should have been, as it stood when
    #: the cheque was recorded. Stored rather than derived, so editing a shift
    #: months later cannot silently rewrite a verdict already reached.
    expected_gross: float | None = None
    #: Signed: positive means the cheque was larger than expected. Null when
    #: there was nothing to expect, which is every contract cheque.
    variance: float | None = None
    notes: str | None = None

    class Config:
        from_attributes = True


class PaychequePreview(BaseModel):
    """What a cheque for this period should come to, before one is entered."""

    job_id: UUID
    period_start: date
    period_end: date
    #: Null for a contract job: there is nothing to predict from hours.
    expected_gross: float | None = None
    shift_count: int = 0
    counted_minutes: int = 0
    #: How many of those shifts are being assumed rather than confirmed, so a
    #: figure built on guesses says so.
    assumed_count: int = 0
    #: Tips paid through payroll, which are inside the gross rather than beside
    #: it. Cash tips are excluded: they never reach a cheque.
    on_cheque_tips: float = 0.0
