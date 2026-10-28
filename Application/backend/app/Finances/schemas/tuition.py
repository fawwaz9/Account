"""Request and response bodies for tuition payments and what a course cost.

A tuition bill is a per-credit rate times the term's credits, plus fees that
belong to no course, less deductions that never touched the account. Only the
net reaches the ledger, as one row; only the rate reaches Grades.
`tuition_service` records payments and answers what each course cost.
"""

from datetime import date
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class TuitionDeduction(BaseModel):
    """Something that lowered a tuition bill without being income, such as a bursary.

    Attributes:
        description: What it was, 1-200 characters.
        amount: Dollars taken off the bill, above 0.
    """

    description: str = Field(..., min_length=1, max_length=200)
    amount: float = Field(..., gt=0)


class TuitionCourse(BaseModel):
    """One course a tuition payment covers, and what its credits make it worth.

    Attributes:
        course_id: The course's id.
        code: The course code.
        name: The course name.
        credits: Its credits.
        share: Its credits times the per-credit rate, gross.
    """

    course_id: UUID
    code: str
    name: str
    credits: float
    share: float


class TuitionCreate(BaseModel):
    """Request body for recording a tuition payment for the current term.

    Attributes:
        account_id: The account it was paid from; one of the user's.
        occurred_on: The day it was paid.
        cost_per_credit: The rate, not the total, 0 or more; rates are summed
            across a term's payments, so two instalments enter half the rate each.
        fees: Mandatory fees that belong to no course, 0 or more; part of the
            ledger row, absent from every course page.
        description: Up to 200 characters; "Tuition <term>" when omitted.
        deductions: Scholarships, bursaries and deposits that lowered the bill.
    """

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
        """Refuse a payment with neither a per-credit cost nor a fee.

        Returns:
            The validated model.

        Raises:
            ValueError: If `cost_per_credit` and `fees` are both 0.
        """
        if self.cost_per_credit == 0 and self.fees == 0:
            raise ValueError("A tuition payment needs a per-credit cost or a fee")
        return self


class TuitionUpdate(BaseModel):
    """Request body correcting a recorded tuition payment; every field is sent.

    The payment and its ledger row change together.

    Attributes:
        account_id: The account it was paid from; one of the user's.
        occurred_on: The day it was paid.
        cost_per_credit: The corrected rate, 0 or more.
        fees: The corrected fees, 0 or more.
        description: Up to 200 characters; "Tuition <term>" when omitted.
        deductions: Replaces every deduction.
        recount_credits: Count the current term's credits as they stand now
            instead of keeping what the bill was for; off by default.
    """

    account_id: UUID
    occurred_on: date
    cost_per_credit: float = Field(..., ge=0)
    fees: float = Field(default=0.0, ge=0)
    description: str | None = Field(default=None, max_length=200)
    deductions: list[TuitionDeduction] = Field(default_factory=list)
    #: Re-count the term's credits as they stand now, rather than keeping what
    #: the bill was for. Off by default: credits_counted is history, and a
    #: correction to the rate should not quietly re-bill a course added since.
    recount_credits: bool = False


class TuitionPreview(BaseModel):
    """The arithmetic of a tuition payment for the current term, before it is written.

    `gross` is what the term is worth, which Grades reports; `payable` is what
    leaves the account. The form shows both.

    Attributes:
        school_year: The user's current school year.
        semester: The user's current semester.
        term_name: The term as a person would write it.
        courses: The current term's courses tuition is charged for (transfer
            credits excluded).
        credits_counted: Those courses' credits, summed.
        cost_per_credit: The rate being previewed.
        gross: `credits_counted` times the rate, before fees and deductions.
        fees: The fees, rounded to cents.
        deductions_total: The deductions, summed.
        payable: `gross` plus fees less deductions: the single ledger row.
        already_recorded_per_credit: The rate already recorded for this term, so
            a second instalment shows the additive model.
        can_record: False when there are no courses to charge a rate against, or
            the deductions exceed the bill.
        reason: Why it cannot be recorded, when it cannot.
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
    """A recorded tuition payment: what its single ledger row was made of.

    Attributes:
        id: The payment's id.
        transaction_id: The ledger row it owns.
        school_year: The school year it paid for.
        semester: The semester it paid for.
        cost_per_credit: The rate it recorded.
        fees: The fees it included.
        credits_counted: The credits it billed, stored when it was recorded.
        occurred_on: The day it was paid.
        deductions: What lowered the bill.
    """

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
        """Pydantic settings: allow building the model from an ORM row."""

        from_attributes = True


class CourseCostLine(BaseModel):
    """One line of a course's cost breakdown.

    Attributes:
        label: The spending category, or "Uncategorised".
        amount: Expenses tagged to the course in that category, in dollars.
    """

    label: str
    amount: float


class CourseCost(BaseModel):
    """What a course cost: its gross share of tuition plus what was bought for it.

    The tuition share is gross (a scholarship reduces what you paid, not what the
    course is worth), so it does not tie out against the ledger and is not meant to.

    Attributes:
        course_id: The course's id.
        credits: Its credits.
        cost_per_credit: The rate recorded for the course's term, summed across
            payments; 0 for a transfer credit.
        tuition_share: `credits` times that rate.
        materials: Expenses tagged to the course on counted accounts, by category,
            largest first.
        materials_total: Those expenses, summed.
        total: `tuition_share` plus `materials_total`.
    """

    course_id: UUID
    credits: float
    cost_per_credit: float = 0.0
    tuition_share: float = 0.0
    materials: list[CourseCostLine] = Field(default_factory=list)
    materials_total: float = 0.0
    total: float = 0.0
