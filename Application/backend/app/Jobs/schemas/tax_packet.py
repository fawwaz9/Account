"""Response bodies for the tax packet: a year's recorded employment income.

Every figure is a sum of what the user entered (paycheques, shift tips and
tuition payments); `tax_packet_service` builds it. It is a summary to check
against official slips, never a filing.
"""
from pydantic import BaseModel


class DeductionLine(BaseModel):
    """One kind of deduction, totalled over a job's cheques for the year.

    Attributes:
        kind: "income_tax", "cpp", "ei" or "other", worked out from the
            deduction's name.
        label: "Income tax", "CPP", "EI", or the deduction's own name for "other".
        amount: The total, in dollars.
    """

    #: income_tax | cpp | ei | other
    kind: str
    label: str
    amount: float


class EmployerYear(BaseModel):
    """One job's recorded pay and tips for the year.

    Attributes:
        job_name: The job's name, or "A deleted job".
        employer: The employer's name, if recorded.
        paycheques: Cheques dated in the year.
        gross: Their gross pay, summed, in dollars.
        deductions: Their deductions by kind, income tax first.
        net: Gross less those deductions.
        cash_tips: Cash tips recorded on the year's shifts.
        other_tips: Tips paid through payroll on the year's shifts, which may
            already sit inside `gross`.
    """

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
    """A calendar year's employment income, summed from what the user recorded.

    Attributes:
        year: The calendar year; a cheque counts in the year it arrived.
        employers: One entry per job with a cheque or tip in the year, highest
            gross first.
        gross: Gross pay across all jobs, in dollars.
        income_tax: Income tax deducted.
        cpp: CPP (or QPP) contributions deducted.
        ei: EI premiums deducted.
        other_deductions: Every other deduction, summed.
        net: Gross less all deductions.
        cash_tips: Cash tips across all jobs.
        tuition_paid: Tuition payments dated in the year, as their ledger amounts:
            after deductions, with fees included.
    """

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
