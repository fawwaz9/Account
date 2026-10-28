"""Service functions that check a recorded paycheque against its shifts.

The check applies BC's overtime and vacation-pay rules (`pay_rules`) and shows
its arithmetic line by line, each line naming its rule. It cuts both ways:
vacation pay is checked on and off the cheque, "short" is judged against the
smaller expectation, and what it cannot see (statutory holidays, unconfirmed
hours) it says. Computed on demand; the cheque's stored `expected_gross` is
never changed.
"""

import uuid

from sqlalchemy.orm import Session

from app._database.models import JobModel, PaychequeModel
from app.Jobs.schemas.job import JobKind
from app.Jobs.schemas.paycheque import PayCheck, PayLine
from app.Jobs.services.job_service import list_shifts
from app.Jobs.services.pay_rules import (
    DAILY_OVERTIME,
    DOUBLE_TIME,
    MULTIPLIER,
    REGULAR,
    RULE,
    WEEKLY_OVERTIME,
    Worked,
    split,
    vacation_percent,
)
from app.shared.money import money

LABEL = {
    REGULAR: "Regular hours",
    DAILY_OVERTIME: "Overtime, past 8 hours in a day",
    DOUBLE_TIME: "Double time, past 12 hours in a day",
    WEEKLY_OVERTIME: "Overtime, past 40 hours in a week",
}
ORDER = (REGULAR, DAILY_OVERTIME, DOUBLE_TIME, WEEKLY_OVERTIME)
VACATION_RULE = "BC Employment Standards Act s.58: 4% of gross wages, 6% after 5 years"
STAT_NOTE = "Statutory holiday pay isn't checked."


def tolerance(expected: float) -> float:
    """Return how far a cheque may differ from the expectation and still match.

    Args:
        expected: The expected gross, in dollars.

    Returns:
        A dollar, or 0.5% of `expected` when that is larger.
    """
    return max(1.0, expected * 0.005)


def check_paycheque(db: Session, user_id: uuid.UUID, paycheque_id: uuid.UUID) -> PayCheck | None:
    """Check one of the user's cheques against the shifts in its pay period.

    Hourly pay is split into regular, overtime and double time at each shift's
    rate; a salaried cheque is compared with the period amount; on-cheque tips are
    added to both. A contract cheque, a cheque with no period, or one whose job is
    gone cannot be checked.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        paycheque_id: The cheque.

    Returns:
        The verdict, its lines and its notes; None when the cheque is not the
        caller's.
    """
    cheque = (
        db.query(PaychequeModel)
        .filter(PaychequeModel.id == paycheque_id, PaychequeModel.user_id == user_id)
        .first()
    )
    if cheque is None:
        return None
    job = db.query(JobModel).filter(JobModel.id == cheque.job_id, JobModel.user_id == user_id).first()
    actual = money(cheque.gross_amount)

    def cannot(summary: str) -> PayCheck:
        """Return a "cannot_check" verdict with only a summary and the actual gross."""
        return PayCheck(paycheque_id=cheque.id, status="cannot_check", summary=summary, actual_gross=actual)

    if job is None:
        return cannot("The job this cheque came from is gone.")
    if cheque.period_start is None or cheque.period_end is None:
        return cannot("No pay period recorded, so there are no shifts to check it against.")
    if job.kind == JobKind.CONTRACT.value:
        return cannot("Contract work is paid as invoiced, so there is nothing to predict.")

    shifts = [
        s for s in (list_shifts(db, user_id, cheque.period_start, cheque.period_end) or [])
        if s.job_id == job.id
    ]
    tips = money(sum(s.tip_amount for s in shifts if not s.tip_is_cash))
    notes: list[str] = []
    lines: list[PayLine] = []

    if job.kind == JobKind.SALARIED.value:
        wages = money(job.period_amount or 0.0)
        lines.append(PayLine(label="Salary for the period", amount=wages))
    else:
        worked = [
            Worked(s.on_date, s.counted_minutes, s.rate_override or job.hourly_rate or 0.0, s.scheduled_start)
            for s in shifts if s.counted_minutes > 0
        ]
        portions = split(worked)
        totals: dict[tuple[str, float], int] = {}
        for portion in portions:
            key = (portion.kind, portion.rate)
            totals[key] = totals.get(key, 0) + portion.minutes
        for kind in ORDER:
            for (k, rate), minutes in sorted(totals.items(), key=lambda item: item[0][1]):
                if k != kind:
                    continue
                paid_rate = rate * MULTIPLIER[kind]
                lines.append(PayLine(
                    label=LABEL[kind], hours=round(minutes / 60, 2), rate=money(paid_rate),
                    amount=money(minutes / 60 * paid_rate), rule=RULE[kind],
                ))
        wages = money(sum(line.amount for line in lines))
        assumed = sum(1 for s in shifts if s.assumed)
        if assumed:
            notes.append(
                f"{assumed} {'shift has' if assumed == 1 else 'shifts have'} not been confirmed, "
                "so scheduled hours are used for them."
            )
        notes.append(
            "Weekly overtime counts only the days inside this pay period, so a week that runs past "
            "either end can only make the expected figure smaller."
        )
        if not shifts:
            notes.append("No shifts were recorded in this period.")

    if tips:
        lines.append(PayLine(label="Tips paid through payroll", amount=tips))
    expected = money(wages + tips)

    percent = vacation_percent(job.started_on, cheque.period_end) if job.kind == JobKind.HOURLY.value else None
    with_vacation = None
    if percent is not None:
        vacation = money(wages * percent / 100)
        with_vacation = money(expected + vacation)
        lines.append(PayLine(
            label=f"Vacation pay, {percent:g}%, if paid on each cheque", amount=vacation, rule=VACATION_RULE,
        ))
        if job.started_on is None:
            notes.append("The job's start date isn't set, so vacation pay is taken at 4%.")
    notes.append(STAT_NOTE)

    status, summary, difference = verdict(actual, expected, with_vacation, percent)
    return PayCheck(
        paycheque_id=cheque.id,
        status=status,
        summary=summary,
        actual_gross=actual,
        expected=expected,
        expected_with_vacation=with_vacation,
        vacation_percent=percent,
        difference=difference,
        lines=lines,
        notes=notes,
    )


def verdict(
    actual: float, expected: float, with_vacation: float | None, percent: float | None,
) -> tuple[str, str, float]:
    """Decide whether a cheque matches, is short, is over, or sits between the two.

    Args:
        actual: The cheque's gross.
        expected: The expectation without vacation pay.
        with_vacation: The expectation with vacation pay on the cheque; None for a
            salaried job.
        percent: The vacation-pay rate used, or None.

    Returns:
        The status, a one-sentence summary and the signed difference against the
        expectation the status is about.
    """
    tol = tolerance(expected)
    if abs(actual - expected) <= tol:
        tail = " Vacation pay isn't on it, so it may be held for later." if percent else ""
        return "as_expected", "Matches the hours." + tail, money(actual - expected)
    if with_vacation is not None and abs(actual - with_vacation) <= tol:
        return (
            "as_expected_with_vacation",
            f"Matches the hours with {percent:g}% vacation pay on the cheque.",
            money(actual - with_vacation),
        )
    if actual < expected - tol:
        return (
            "short",
            f"Looks {money_text(expected - actual)} short of what the hours come to.",
            money(actual - expected),
        )
    ceiling = with_vacation if with_vacation is not None else expected
    if actual > ceiling + tol:
        return "over", f"{money_text(actual - ceiling)} more than the hours come to.", money(actual - ceiling)
    return (
        "unclear",
        "Between the two expected figures: check the vacation-pay line on the stub.",
        money(actual - expected),
    )


def money_text(amount: float) -> str:
    """Format dollars for a sentence, such as "$1,234.50".

    Args:
        amount: Dollars.

    Returns:
        The amount with a dollar sign, thousands separators and cents.
    """
    return f"${amount:,.2f}"
