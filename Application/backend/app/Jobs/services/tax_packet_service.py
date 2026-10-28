"""Service functions for the tax packet: a calendar year's recorded employment income.

Built only from what the user recorded (paycheques, shift tips and tuition
payments); the app never reads a T4. A cheque counts in the year it arrived,
and a deduction is sorted by its own name into income tax, CPP, EI or other.
"""
import re
import uuid
from collections import defaultdict
from datetime import date

from sqlalchemy.orm import Session

from app._database.models import (
    JobModel, PaychequeModel, ShiftRecordModel, TransactionModel, TuitionPaymentModel,
)
from app.Jobs.schemas.tax_packet import DeductionLine, EmployerYear, TaxPacket
from app.shared.dates import user_for

KIND_LABELS = {"income_tax": "Income tax", "cpp": "CPP", "ei": "EI"}


def deduction_kind(description: str) -> str:
    """Sort a deduction into a tax-packet kind by its description.

    Args:
        description: The deduction's name as entered.

    Returns:
        "cpp" (CPP or QPP), "ei", "income_tax" (anything mentioning tax) or
        "other".
    """
    text = description.lower()
    if re.search(r"\b(cpp|qpp)\d?\b|canada pension|pension plan", text):
        return "cpp"
    if re.search(r"\bei\b|employment insurance", text):
        return "ei"
    if "tax" in text:
        return "income_tax"
    return "other"


def _money(value: float) -> float:
    """Round to cents, normalising negative zero; a copy of `shared.money.money`."""
    return round(value + 0.0, 2)


def tax_packet(db: Session, user_id: uuid.UUID, year: int) -> TaxPacket | None:
    """Return a year's recorded pay per job, its deductions, tips and tuition paid.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        year: The calendar year.

    Returns:
        The packet, one entry per job with a cheque or a tip that year (highest
        gross first); None when the user does not exist.
    """
    if user_for(db, user_id) is None:
        return None
    first, last = date(year, 1, 1), date(year, 12, 31)
    jobs = {job.id: job for job in db.query(JobModel).filter(JobModel.user_id == user_id)}
    cheques = (
        db.query(PaychequeModel)
        .filter(PaychequeModel.user_id == user_id, PaychequeModel.occurred_on >= first,
                PaychequeModel.occurred_on <= last)
        .all()
    )
    tips = (
        db.query(ShiftRecordModel)
        .filter(ShiftRecordModel.user_id == user_id, ShiftRecordModel.on_date >= first,
                ShiftRecordModel.on_date <= last, ShiftRecordModel.tip_amount > 0)
        .all()
    )

    by_job: dict = defaultdict(lambda: {"count": 0, "gross": 0.0, "deductions": defaultdict(float),
                                        "cash_tips": 0.0, "other_tips": 0.0})
    for cheque in cheques:
        entry = by_job[cheque.job_id]
        entry["count"] += 1
        entry["gross"] += cheque.gross_amount or 0.0
        for deduction in cheque.deductions:
            kind = deduction_kind(deduction.description)
            label = KIND_LABELS.get(kind, deduction.description.strip())
            entry["deductions"][(kind, label)] += deduction.amount or 0.0
    for shift in tips:
        by_job[shift.job_id]["cash_tips" if shift.tip_is_cash else "other_tips"] += shift.tip_amount

    order = {"income_tax": 0, "cpp": 1, "ei": 2, "other": 3}
    employers = []
    for job_id, entry in by_job.items():
        job = jobs.get(job_id)
        lines = [DeductionLine(kind=kind, label=label, amount=_money(amount))
                 for (kind, label), amount in sorted(entry["deductions"].items(), key=lambda kv: (order[kv[0][0]], kv[0][1]))]
        employers.append(EmployerYear(
            job_name=job.name if job else "A deleted job", employer=job.employer if job else None,
            paycheques=entry["count"], gross=_money(entry["gross"]), deductions=lines,
            net=_money(entry["gross"] - sum(line.amount for line in lines)),
            cash_tips=_money(entry["cash_tips"]), other_tips=_money(entry["other_tips"]),
        ))
    employers.sort(key=lambda e: (-e.gross, e.job_name))

    def total(kind):
        """Return one deduction kind's total across every job, rounded to cents."""
        return _money(sum(line.amount for e in employers for line in e.deductions if line.kind == kind))

    tuition = (
        db.query(TransactionModel.amount)
        .join(TuitionPaymentModel, TuitionPaymentModel.transaction_id == TransactionModel.id)
        .filter(TuitionPaymentModel.user_id == user_id, TuitionPaymentModel.occurred_on >= first,
                TuitionPaymentModel.occurred_on <= last)
        .all()
    )
    return TaxPacket(
        year=year, employers=employers,
        gross=_money(sum(e.gross for e in employers)),
        income_tax=total("income_tax"), cpp=total("cpp"), ei=total("ei"), other_deductions=total("other"),
        net=_money(sum(e.net for e in employers)),
        cash_tips=_money(sum(e.cash_tips for e in employers)),
        tuition_paid=_money(sum(abs(amount or 0.0) for (amount,) in tuition)),
    )
