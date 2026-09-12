"""What a tuition payment is made of.

Deliberately separate from a plain transaction: a tuition bill is a rate times a
number of credits, plus fees that belong to no course, less deductions that never
touched the account. Only the net reaches the ledger, and only the rate reaches
Grades.
"""

from datetime import date
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class TuitionDeduction(BaseModel):
    """Something that lowered the bill without being income.

    A scholarship, a bursary, a deposit paid earlier. Named, because "why was
    this cheaper than the sticker price" is the question being answered.
    """

    description: str = Field(..., min_length=1, max_length=200)
    amount: float = Field(..., gt=0)


class TuitionCourse(BaseModel):
    """One course the payment covers, and what its credits make it worth."""

    course_id: UUID
    code: str
    name: str
    credits: float
    share: float


class TuitionCreate(BaseModel):
    account_id: UUID
    occurred_on: date
    #: The rate, not the total. Summed across a term's payments, so two
    #: instalments means entering half the rate twice.
    cost_per_credit: float = Field(..., ge=0)
    #: Mandatory, but not a cost of any one course -- a U-Pass is not a cost of
    #: CPSC 210. Part of the ledger line, absent from every course page.
    fees: float = Field(default=0.0, ge=0)
    description: str | None = Field(default=None, max_length=200)
    deductions: list[TuitionDeduction] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_amounts(self):
        if self.cost_per_credit == 0 and self.fees == 0:
            raise ValueError("A tuition payment needs a per-credit cost or a fee")
        return self


class TuitionPreview(BaseModel):
    """The arithmetic, before anything is written.

    Both totals are here on purpose. `gross` is what the term is worth and is
    what Grades will report; `payable` is what leaves the account. They are
    different numbers and the form should show both rather than implying one.
    """

    school_year: int | None = None
    semester: str | None = None
    #: The term as a person would write it. school_year is a year of
    #: standing, so the client cannot build this from the parts.
    term_name: str = "your current term"
    courses: list[TuitionCourse] = Field(default_factory=list)
    credits_counted: float = 0.0
    cost_per_credit: float = 0.0
    #: credits x rate, before fees and before anything is taken off.
    gross: float = 0.0
    fees: float = 0.0
    deductions_total: float = 0.0
    #: What the single ledger row will be for.
    payable: float = 0.0
    #: Per-credit rate already recorded for this term, so a second instalment
    #: makes the additive model visible instead of a trap.
    already_recorded_per_credit: float = 0.0
    can_record: bool = True
    reason: str | None = None


class TuitionPayment(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    transaction_id: UUID
    school_year: int | None = None
    semester: str | None = None
    cost_per_credit: float
    fees: float
    credits_counted: float
    occurred_on: date
    deductions: list[TuitionDeduction] = Field(default_factory=list)

    class Config:
        from_attributes = True


class CourseCostLine(BaseModel):
    """One row of what a course cost, so the page can show a breakdown."""

    label: str
    amount: float


class CourseCost(BaseModel):
    """What a course cost, which is a Grades question and not a ledger one.

    The tuition share is gross: a scholarship reduces what you paid, not what the
    course is worth. It therefore will not tie out against the ledger, and is not
    meant to.
    """

    course_id: UUID
    credits: float
    cost_per_credit: float = 0.0
    tuition_share: float = 0.0
    materials: list[CourseCostLine] = Field(default_factory=list)
    materials_total: float = 0.0
    total: float = 0.0
