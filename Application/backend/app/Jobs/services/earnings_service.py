"""What the jobs came to: hours, money, and the gap between the two.

One service answering four questions off one window, in the same shape as
`load_service`: they are the same question asked differently, and splitting them
across four services would mean four passes over the same shifts.

The distinction that runs through all of it is **earned** against **paid**.
Earned comes from the shifts and is a prediction; paid comes from cheques that
actually arrived. Collapsing them into one figure would hide exactly the thing
this page exists to show -- that a fortnight of work has not been paid for yet,
or was paid short.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app._database.models import (
    JobModel,
    PaychequeDeductionModel,
    PaychequeModel,
    UserModel,
)
from app.Calendar.services.load_service import week_load, week_of
from app.Grades.utils.terms import term_dates
from app.Jobs.schemas.earnings import (
    EarningsSummary,
    EarningsWindow,
    EffectiveRate,
    HoursAgainstClasses,
    JobEarnings,
    UpcomingPay,
)
from app.Jobs.schemas.job import JobKind
from app.Jobs.services.job_service import list_shifts, next_pay_on
from app.Jobs.services.pay_schedule import pay_dates
from app.shared.dates import user_today
from app.shared.money import money


def earned_from_shifts(job: JobModel, shifts) -> tuple[float, float]:
    """What a job's shifts in a window earned, and the cash tips beside them.

    Hourly multiplies out. Salaried returns nothing here: its pay comes from
    pay periods rather than hours, and dividing a salary by hours worked would
    make a long week read as a pay cut. Contract returns nothing for the same
    reason it predicts nothing -- you invoiced it.

    The `kind` check is defensive rather than load-bearing: `check_pay_fields`
    already clears `hourly_rate` on anything that is not hourly, so the
    multiplication would come to zero anyway. It is kept because relying on that
    means this function is only correct as long as another one stays correct,
    and because it is what stops on-cheque tips being added to a salary.
    """
    cash_tips = money(sum(s.tip_amount for s in shifts if s.tip_is_cash))

    if job.kind != JobKind.HOURLY.value:
        return 0.0, cash_tips

    earned = 0.0
    for shift in shifts:
        rate = shift.rate_override or job.hourly_rate or 0.0
        earned += shift.counted_minutes / 60 * rate
    # Tips paid through payroll are part of what the job earned, and will arrive
    # inside a cheque's gross rather than beside it.
    earned += sum(s.tip_amount for s in shifts if not s.tip_is_cash)
    return money(earned), cash_tips


def cheques_in(db: Session, user_id: uuid.UUID, start: date, end: date):
    return (
        db.query(PaychequeModel)
        .filter(
            PaychequeModel.user_id == user_id,
            PaychequeModel.occurred_on >= start,
            PaychequeModel.occurred_on <= end,
        )
        .all()
    )


def deducted_from(db: Session, cheques) -> float:
    if not cheques:
        return 0.0

    rows = (
        db.query(PaychequeDeductionModel)
        .filter(PaychequeDeductionModel.paycheque_id.in_([c.id for c in cheques]))
        .all()
    )
    return money(sum(row.amount for row in rows))


def window_earnings(
    db: Session,
    user_id: uuid.UUID,
    jobs: list[JobModel],
    label: str,
    start: date,
    end: date,
    anchor: date,
) -> EarningsWindow:
    """One window, every job, hours and money side by side.

    `anchor` is passed down rather than left to default, so whether a shift
    counts as past is judged against the day being reported on. Without it the
    figures move with the wall clock, which also makes them impossible to test
    at a fixed date.
    """
    shifts = list_shifts(db, user_id, start, end, on_day=anchor) or []
    by_job: dict[uuid.UUID, list] = {}
    for shift in shifts:
        by_job.setdefault(shift.job_id, []).append(shift)

    cheques = cheques_in(db, user_id, start, end)
    cheques_by_job: dict[uuid.UUID, list] = {}
    for cheque in cheques:
        cheques_by_job.setdefault(cheque.job_id, []).append(cheque)

    per_job: list[JobEarnings] = []
    for job in jobs:
        mine = by_job.get(job.id, [])
        paid_to_me = cheques_by_job.get(job.id, [])
        periods = periods_in(job, start, end) if job.kind == JobKind.SALARIED.value else 0
        earned, cash = earned_from_shifts(job, mine)
        if periods:
            earned = money(earned + periods * (job.period_amount or 0.0))

        # A cheque counts a job in even when no shift does. Pay arrives for work
        # done before the window opened, so a job can be the only thing in the
        # paid breakdown while contributing no hours at all -- dropping it here
        # would lose money that the window's own total still includes, and the
        # per-job rows would not add up to the headline.
        if not mine and earned == 0.0 and not paid_to_me:
            continue

        job_gross = money(sum(c.gross_amount for c in paid_to_me))
        job_deducted = deducted_from(db, paid_to_me)

        per_job.append(JobEarnings(
            job_id=job.id,
            job_name=job.name,
            kind=job.kind,
            shift_count=len(mine),
            counted_minutes=sum(s.counted_minutes for s in mine),
            assumed_count=sum(1 for s in mine if s.assumed),
            gross_earned=earned,
            cash_tips=cash,
            gross_paid=job_gross,
            deducted=job_deducted,
            net_paid=money(job_gross - job_deducted),
        ))

    gross_paid = money(sum(c.gross_amount for c in cheques))
    deducted = deducted_from(db, cheques)

    return EarningsWindow(
        label=label,
        starts_on=start,
        ends_on=end,
        counted_minutes=sum(entry.counted_minutes for entry in per_job),
        gross_earned=money(sum(entry.gross_earned for entry in per_job)),
        cash_tips=money(sum(entry.cash_tips for entry in per_job)),
        gross_paid=gross_paid,
        deducted=deducted,
        net_paid=money(gross_paid - deducted),
        per_job=per_job,
    )


def periods_in(job: JobModel, start: date, end: date) -> int:
    """How many of a salaried job's pay dates fall inside the window.

    Zero without a pay rule, which is honest: a salaried job whose schedule
    nobody entered has no way to say what a fortnight of it was worth.
    """
    return len(pay_dates(job, start, end))


def effective_rate(
    db: Session, user_id: uuid.UUID, since: date, until: date, anchor: date
) -> EffectiveRate:
    """What an hour actually paid, after everything taken off.

    Measured over the periods cheques actually covered, not over every hour
    worked: hours not yet paid for would otherwise drag the rate down and read
    as a pay cut rather than as a cheque still to come.
    """
    cheques = [
        cheque
        for cheque in cheques_in(db, user_id, since, until)
        if cheque.period_start and cheque.period_end
    ]
    if not cheques:
        return EffectiveRate()

    minutes = 0
    for cheque in cheques:
        shifts = list_shifts(
            db, user_id, cheque.period_start, cheque.period_end, on_day=anchor
        ) or []
        minutes += sum(s.counted_minutes for s in shifts if s.job_id == cheque.job_id)

    if minutes == 0:
        return EffectiveRate()

    gross = sum(cheque.gross_amount for cheque in cheques)
    deducted = deducted_from(db, cheques)
    hours = minutes / 60

    return EffectiveRate(
        net_per_hour=money((gross - deducted) / hours),
        gross_per_hour=money(gross / hours),
        deduction_percent=round(deducted / gross * 100, 1) if gross else None,
        paid_minutes=minutes,
    )


def upcoming_pay(db: Session, user_id: uuid.UUID, jobs: list[JobModel], anchor: date):
    """Work no cheque has covered yet, and when one is next due."""
    rows: list[UpcomingPay] = []

    for job in jobs:
        if job.ended_on is not None:
            continue

        last = (
            db.query(PaychequeModel)
            .filter(
                PaychequeModel.user_id == user_id,
                PaychequeModel.job_id == job.id,
                PaychequeModel.period_end.isnot(None),
            )
            .order_by(PaychequeModel.period_end.desc())
            .first()
        )
        since = (last.period_end + timedelta(days=1)) if last else (job.started_on or anchor)
        if since > anchor:
            rows.append(UpcomingPay(
                job_id=job.id, job_name=job.name,
                next_pay_on=next_pay_on(job, anchor),
            ))
            continue

        shifts = [
            shift
            for shift in (list_shifts(db, user_id, since, anchor, on_day=anchor) or [])
            if shift.job_id == job.id
        ]
        minutes = sum(s.counted_minutes for s in shifts)
        earned, _ = earned_from_shifts(job, shifts)

        rows.append(UpcomingPay(
            job_id=job.id,
            job_name=job.name,
            unpaid_minutes=minutes,
            unpaid_estimate=earned if job.kind == JobKind.HOURLY.value else None,
            next_pay_on=next_pay_on(job, anchor),
        ))

    return rows


def hours_against_classes(db: Session, user_id: uuid.UUID, anchor: date):
    """Paid work beside timetabled hours for the current week."""
    start = week_of(anchor)
    end = start + timedelta(days=6)
    load = week_load(db, user_id, start, end)
    if load is None:
        return None

    return HoursAgainstClasses(
        starts_on=start,
        ends_on=end,
        work_minutes=load.work_minutes,
        class_minutes=load.class_minutes,
        task_minutes=load.estimated_minutes,
    )


def earnings_summary(db: Session, user_id: uuid.UUID, on_day: date | None = None):
    """The whole jobs page, from one pass."""
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None

    anchor = on_day or user_today(db, user_id)
    jobs = db.query(JobModel).filter(JobModel.user_id == user_id).all()

    week_start = anchor - timedelta(days=6)
    month_start = anchor.replace(day=1)

    # The term's own dates, through the one accessor Grades and Finances also
    # read. This module used to restate the rule -- earliest start and latest
    # end across the term's courses -- and its own docstring said so. Restating
    # is what let the two drift: once Finances started measuring the term
    # itself, Jobs went on measuring the teaching weeks, and "This term" landed
    # on Sep 9 while the budget's term began Sep 1.
    term = None
    span = term_dates(
        user.current_semester, user.current_school_year, user.first_year_calendar_year
    )
    if span is not None:
        term_start, term_end = span
        # Clamped at today, because earnings cannot be reported for a stretch of
        # term that has not happened yet.
        if term_start <= anchor:
            term = window_earnings(
                db, user_id, jobs, "This term", term_start, min(term_end, anchor), anchor
            )

    return EarningsSummary(
        week=window_earnings(db, user_id, jobs, "Past week", week_start, anchor, anchor),
        month=window_earnings(db, user_id, jobs, "This month", month_start, anchor, anchor),
        term=term,
        effective_rate=effective_rate(
            db, user_id, anchor.replace(month=1, day=1), anchor, anchor
        ),
        upcoming=upcoming_pay(db, user_id, jobs, anchor),
        this_week=hours_against_classes(db, user_id, anchor),
    )
