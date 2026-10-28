"""Request and response bodies for paycheques, their deductions, previews and checks.

A paycheque records gross pay and named deductions; only the net reaches the
ledger, split across accounts like any deposit. `paycheque_service` records and
corrects cheques, and `paycheck_service` checks one against its shifts under
BC's pay rules.
"""

from datetime import date
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from app.Finances.schemas.deposit import DepositAllocation

#: Nothing one cheque pays is beyond this, and a figure past it is a slipped
#: digit rather than a wage.
MAX_CHEQUE = 1_000_000.0


class DeductionEntry(BaseModel):
    """One deduction taken off a cheque before it arrived, as entered.

    Attributes:
        description: What it was ("Income tax", "CPP"), 1-120 characters; the tax
            packet sorts deductions by this name.
        amount: Dollars deducted, positive, at most 1,000,000.
    """

    description: str = Field(..., min_length=1, max_length=120)
    #: Positive. The sign is in the name.
    amount: float = Field(..., gt=0, le=MAX_CHEQUE)


class PaychequeBase(BaseModel):
    """Fields of a cheque as entered.

    Attributes:
        job_id: The job it paid for; one of the user's jobs.
        occurred_on: The day it arrived, which also dates its ledger rows.
        gross_amount: Gross pay in dollars, above 0 and at most 1,000,000.
        period_start: First day of the work it covers; give both ends or neither.
        period_end: Last day of the work it covers, not before `period_start`.
        deductions: Up to 20 deductions, together less than the gross.
        notes: Up to 2000 characters.
    """

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
        """Check the pay period and that the deductions leave something to pay.

        Returns:
            The validated model.

        Raises:
            ValueError: If only one end of the period is given, the period ends before
                it starts, or the deductions total the gross or more.
        """
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
    """Request body for recording a cheque that arrived.

    With no allocations the net (gross less deductions) splits by each account's
    income share; allocations override that for this cheque.

    Attributes:
        allocations: Explicit amounts for the net per account, each account once.
    """

    allocations: list[DepositAllocation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_allocations(self):
        """Check that given allocations come to the net and name each account once.

        The comparison is a float difference against 0.01, so allocations a cent away
        from the net can pass.

        Returns:
            The validated model.

        Raises:
            ValueError: If the allocations differ from the net by more than 0.01, or an
                account appears twice.
        """
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
    """Request body correcting a cheque; only the fields sent are changed.

    The cheque's ledger rows are always rewritten: the net is split again, by
    `allocations` if sent and otherwise by today's income shares. `expected_gross`
    is never recomputed.

    Attributes:
        occurred_on: New arrival date.
        gross_amount: New gross, above 0 and at most 1,000,000.
        period_start: New first day of the period.
        period_end: New last day of the period; the service checks the order.
        deductions: Replaces every deduction (up to 20); omit to keep them.
        allocations: How to split the net this time; not checked against the net.
        notes: New notes; null clears them.
    """

    occurred_on: date | None = None
    gross_amount: float | None = Field(default=None, gt=0, le=MAX_CHEQUE)
    period_start: date | None = None
    period_end: date | None = None
    deductions: list[DeductionEntry] | None = Field(default=None, max_length=20)
    allocations: list[DepositAllocation] | None = None
    notes: str | None = Field(default=None, max_length=2000)


class Deduction(DeductionEntry):
    """A recorded deduction: the `DeductionEntry` fields plus its id.

    Attributes:
        id: The deduction's id.
    """

    id: UUID = Field(default_factory=uuid4)

    class Config:
        """Pydantic settings: allow building the model from an ORM row."""

        from_attributes = True


class Paycheque(BaseModel):
    """A recorded cheque as the API returns it.

    Attributes:
        id: The cheque's id.
        job_id: The job it paid for.
        job_name: That job's name; empty when the job is gone.
        occurred_on: The day it arrived.
        gross_amount: Gross pay, in dollars.
        deductions: Its deductions.
        net_amount: Gross less every deduction.
        period_start: First day of the work it covers.
        period_end: Last day of the work it covers.
        expected_gross: What the period's shifts said it should be when it was
            recorded, frozen then; None without a period, and for a contract job.
        variance: `gross_amount` less `expected_gross`, signed (positive means the
            cheque was larger); None without an expectation.
        notes: Free text.
    """

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
        """Pydantic settings: allow building the model from an ORM row."""

        from_attributes = True


class PaychequePreview(BaseModel):
    """What a cheque for a period should come to, from the shifts in it.

    Attributes:
        job_id: The job.
        period_start: First day of the period.
        period_end: Last day of the period.
        expected_gross: For an hourly job, the hours with BC overtime at each
            shift's rate plus on-cheque tips; for a salaried one, the period amount
            plus on-cheque tips; None for a contract job. Vacation pay is left out.
        shift_count: The job's shift occurrences in the period.
        counted_minutes: Minutes those shifts count for.
        assumed_count: Past shifts never confirmed, counted at scheduled hours.
        on_cheque_tips: Tips paid through payroll in the period; cash tips never
            reach a cheque and are left out.
    """

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


class PayLine(BaseModel):
    """One line of a pay check's arithmetic, naming the rule it came from.

    Attributes:
        label: What the line is, such as "Regular hours".
        hours: Hours on the line; None for a line that is not hours times a rate.
        rate: Dollars per hour paid on the line, multiplier included; None for a
            line that is not hours times a rate.
        amount: The line's dollars.
        rule: The statute the line applies; None for regular hours, salary and
            tips.
    """

    label: str
    #: Null for a line that is not hours times a rate (tips, vacation pay).
    hours: float | None = None
    rate: float | None = None
    amount: float
    rule: str | None = None


class PayCheck(BaseModel):
    """A cheque checked against its shifts under BC's pay rules, worked out on demand.

    Unlike the stored `expected_gross`, it reflects the shifts as they are now. A
    match means within a dollar, or 0.5% of a large cheque.

    Attributes:
        paycheque_id: The cheque checked.
        status: "as_expected", "as_expected_with_vacation", "short", "over",
            "unclear" (between the two expectations) or "cannot_check" (no period,
            a contract job, or a job that is gone).
        summary: One sentence for the list, such as "Looks $38.00 short of what
            the hours come to."
        actual_gross: The cheque's gross.
        expected: Wages with overtime (or the salary) plus on-cheque tips, without
            vacation pay; None when it cannot be checked.
        expected_with_vacation: `expected` plus vacation pay paid on this cheque;
            hourly jobs only.
        vacation_percent: 4, or 6 after five years with the employer; hourly jobs
            only.
        difference: The gross less whichever expectation the verdict is about;
            positive means the cheque is larger.
        lines: The arithmetic, line by line.
        notes: What was assumed and what was not checked.
    """

    paycheque_id: UUID
    #: as_expected | as_expected_with_vacation | short | over | unclear | cannot_check
    status: str
    #: One sentence, for the list: "Looks $38.00 short." Never certain.
    summary: str
    actual_gross: float
    #: The hours, overtime and on-cheque tips, vacation pay not included.
    expected: float | None = None
    #: The same, with vacation pay paid on this cheque.
    expected_with_vacation: float | None = None
    vacation_percent: float | None = None
    #: Positive: the cheque is larger. Measured against whichever expectation
    #: the verdict is about.
    difference: float | None = None
    lines: list[PayLine] = Field(default_factory=list)
    #: What was assumed, and what was not checked.
    notes: list[str] = Field(default_factory=list)
