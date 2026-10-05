"""Is this cheque right? The shifts, BC's rules, and the arithmetic shown.

Phase 1 item 11 (account-vision.md §13.11): "Your Oct 15 cheque looks $38
short -- Tuesday was 9 hours, overtime may apply." Unique to this app, because
only here do the shifts and the cheques live together.

It cuts both ways (§15): a false "you're short" erodes trust as fast as a
missed real one. So:

* **Every figure shows its working,** line by line, each naming its rule.
* **Vacation pay is checked both ways.** The app does not know whether an
  employer pays the 4% on each cheque or holds it, and guessing wrong would
  flag every cheque. A cheque matching either expectation matches; one
  between the two says to check the vacation-pay line.
* **Short is measured against the smaller expectation** (no vacation pay on the
  cheque), so a "short" flag never depends on that guess.
* **What it cannot see, it says:** statutory holidays are not checked, hours
  from unconfirmed shifts are assumed from the schedule, and a week that runs
  past the pay period only counts the days inside it -- which can only ever
  make the expectation smaller, never manufacture a shortfall.

Computed on demand from the shifts as they are now. The cheque's stored
`expected_gross` is the verdict reached when it was recorded, and this does not
change it.
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
    """Rounding on a real cheque is cents, sometimes a dollar; never a percent."""
    return max(1.0, expected * 0.005)


def check_paycheque(db: Session, user_id: uuid.UUID, paycheque_id: uuid.UUID) -> PayCheck | None:
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
    return f"${amount:,.2f}"
