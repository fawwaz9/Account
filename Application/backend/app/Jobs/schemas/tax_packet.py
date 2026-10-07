"""A year's employment income from what you recorded (Phase 2 item 14, D21)."""
from pydantic import BaseModel


class DeductionLine(BaseModel):
    #: income_tax | cpp | ei | other
    kind: str
    label: str
    amount: float


class EmployerYear(BaseModel):
    job_name: str
    employer: str | None
    paycheques: int
    gross: float
    deductions: list[DeductionLine]
    net: float
    #: Tips recorded on shifts. Cash tips were in hand; the rest came through
    #: payroll and may already be inside the gross above.
    cash_tips: float
    other_tips: float


class TaxPacket(BaseModel):
    """A summary for your own records, never a filing: every figure is a sum of
    what you entered, and the page says to check it against your slips."""

    year: int
    employers: list[EmployerYear]
    gross: float
    income_tax: float
    cpp: float
    ei: float
    other_deductions: float
    net: float
    cash_tips: float
    tuition_paid: float
