"""Service functions for the year plan: one running balance to the school year's end.

The forecast's engine pointed at a wider question: all liquid money (spending,
savings and emergency accounts that count) from today to the Winter term's last
day, rolled up by month. Given a target balance and date it is solved backwards
into the extra weekly hours at the main hourly job. Comparing saved plans with
what happened lives in `plan_review_service`.
"""

import math
import uuid
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app._database.models import AccountModel, JobModel, UserModel
from app.Finances.schemas.plan import AnnualPlan, Goal, PlanMonth, Scenario
from app.Finances.services.account_service import balances_by_account
from app.Finances.services.forecast_service import (
    LIQUID_KINDS,
    MAX_DAYS,
    DEDUCTION_LOOKBACK_DAYS,
    daily_one_off_spending,
    days_of_history,
    debt_account_ids,
    income_share_note,
    money_text,
    pay_events,
    project,
    recurring_events,
    spendable_income_share,
    tuition_transaction_ids,
)
from app.Grades.utils.terms import term_dates
from app.Jobs.schemas.job import JobKind
from app.Jobs.services.earnings_service import effective_rate
from app.shared.dates import user_today
from app.shared.money import money

#: Extra weekly hours the solver prices, so the answer reads as choices.
SCENARIO_HOURS = (0, 4, 8, 12, 16)


def plan(
    db: Session,
    user_id: uuid.UUID,
    on_day: date | None = None,
    target: float | None = None,
    target_on: date | None = None,
) -> AnnualPlan | None:
    """Return the year plan, and the hours a target needs when one is given.

    Args:
        db: Open database session.
        user_id: Whose money.
        on_day: The day to plan from; defaults to the user's today.
        target: A balance to reach by the plan's end, in dollars; None for no goal.
        target_on: The date the plan runs to instead of the school year's end.

    Returns:
        The monthly rows, the ending and lowest balances, the goal when it can be
        priced, and every assumption; None when the user does not exist.

    Raises:
        ValueError: If `target_on` is not after today or is more than `MAX_DAYS`
            ahead.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None

    anchor = on_day or user_today(db, user_id)
    assumptions: list[str] = []
    if target_on is not None:
        if target_on <= anchor:
            raise ValueError("The target date has to be after today")
        if target_on > anchor + timedelta(days=MAX_DAYS):
            raise ValueError(f"A plan cannot run more than {MAX_DAYS} days ahead")
        ends_on = target_on
    else:
        ends_on, known = school_year_end(user, anchor)
        if not known:
            assumptions.append("Your school year isn't known, so the plan runs to April 30.")

    liquid = liquid_accounts(db, user_id)
    liquid_ids = set(liquid)
    starting = money(sum(liquid.values()))

    excluded = tuition_transaction_ids(db, user_id)
    history_days = days_of_history(db, user_id, anchor)
    daily = daily_one_off_spending(
        db, user_id, liquid_ids | debt_account_ids(db, user_id), anchor, history_days, excluded,
    )
    if history_days:
        assumptions.append(
            f"Day-to-day spending continues at {money_text(daily)} a day, your average over the "
            f"last {history_days} days (standing instructions and tuition counted separately)."
        )
    else:
        assumptions.append("No spending history yet, so day-to-day spending is counted as $0.")

    raw_share = spendable_income_share(db, user_id, liquid_ids)
    share = 1.0 if raw_share is None else raw_share
    events = recurring_events(db, user_id, liquid_ids, anchor, ends_on, share)
    if events:
        assumptions.append("Standing instructions run as scheduled.")
    events += pay_events(db, user_id, liquid_ids, anchor, ends_on, share, assumptions)
    if any(event.split for event in events) and (raw_share is None or raw_share < 1):
        assumptions.append(income_share_note(raw_share).replace("spending accounts", "these accounts"))
    assumptions.append(
        "Liquid money is spending, savings and emergency accounts; investments and debt are left out."
    )
    assumptions.append("Tuition instalments and anything else not yet scheduled aren't included.")

    points, _, lowest, lowest_on = project(starting, daily, events, anchor, ends_on)
    months = monthly(points, events, daily, anchor)
    ending = points[-1].balance

    goal = None
    if target is not None:
        goal = solve(db, user_id, anchor, ends_on, target, ending, share, assumptions)

    return AnnualPlan(
        starts_on=anchor,
        ends_on=ends_on,
        starting_balance=starting,
        months=months,
        ending_balance=ending,
        lowest_balance=lowest,
        lowest_on=lowest_on,
        goal=goal,
        assumptions=assumptions,
    )


def school_year_end(user: UserModel, anchor: date) -> tuple[date, bool]:
    """Return the last day of the school year's Winter term, or the next April 30.

    Within 30 days of that Winter's end, the next school year's is used instead, so
    a plan made in spring or summer still looks ahead.

    Args:
        user: The user, for their school year and first-year anchor.
        anchor: Today.

    Returns:
        The end date and whether it came from the user's school year.
    """
    if user.current_school_year is not None:
        span = term_dates("Winter", user.current_school_year, user.first_year_calendar_year)
        if span is not None:
            end = span[1]
            if end <= anchor + timedelta(days=30):
                nxt = term_dates("Winter", user.current_school_year + 1, user.first_year_calendar_year)
                end = nxt[1] if nxt else end
            if anchor + timedelta(days=30) < end <= anchor + timedelta(days=MAX_DAYS):
                return end, True
    year = anchor.year if anchor < date(anchor.year, 4, 1) else anchor.year + 1
    return date(year, 4, 30), False


def liquid_accounts(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, float]:
    """Return the balances of the user's counted, unarchived liquid accounts, by id.

    Args:
        db: Open database session.
        user_id: Owner of the rows.

    Returns:
        Balance in dollars by account id; empty when there are none.
    """
    accounts = (
        db.query(AccountModel)
        .filter(
            AccountModel.user_id == user_id,
            AccountModel.archived.is_(False),
            AccountModel.kind.in_(LIQUID_KINDS),
            AccountModel.counts_toward_net_worth.is_(True),
        )
        .all()
    )
    balances = balances_by_account(db, user_id)
    return {account.id: balances.get(account.id, 0.0) for account in accounts}


def monthly(points, events, daily: float, anchor: date) -> list[PlanMonth]:
    """Roll the daily projection up into the plan's monthly rows.

    Args:
        points: The daily balances.
        events: The dated movements, signed.
        daily: Day-to-day spending per day, charged from the day after `anchor`.
        anchor: Today.

    Returns:
        One row per month the points cover, with money in, money out (positive)
        and the last balance seen in that month.
    """
    money_in: dict[date, float] = defaultdict(float)
    money_out: dict[date, float] = defaultdict(float)
    for event in events:
        key = event.on_date.replace(day=1)
        if event.amount > 0:
            money_in[key] += event.amount
        else:
            money_out[key] -= event.amount

    end_balance: dict[date, float] = {}
    for point in points:
        key = point.on_date.replace(day=1)
        end_balance[key] = point.balance  # the last day seen wins
        if point.on_date > anchor:
            money_out[key] += daily

    return [
        PlanMonth(
            month=key,
            money_in=money(money_in.get(key, 0.0)),
            money_out=money(money_out.get(key, 0.0)),
            end_balance=balance,
        )
        for key, balance in sorted(end_balance.items())
    ]


def solve(
    db: Session,
    user_id: uuid.UUID,
    anchor: date,
    ends_on: date,
    target: float,
    base_end: float,
    share: float,
    assumptions: list[str],
) -> Goal | None:
    """Return the extra weekly hours a target needs, priced at the main hourly job.

    The main job is the first current, unarchived hourly job with a rate, in the
    user's order. One extra hour adds the rate after the recent deduction rate,
    times the liquid accounts' share of the income split. Adds its assumption.

    Args:
        db: Open database session.
        user_id: Whose jobs.
        anchor: Today.
        ends_on: The target date.
        target: The balance wanted, in dollars.
        base_end: The plan's ending balance with no extra work.
        share: The liquid accounts' share of the income split.
        assumptions: The list to add the assumption sentence to.

    Returns:
        The goal with scenarios; None when no hourly job can price an hour.
    """
    job = (
        db.query(JobModel)
        .filter(
            JobModel.user_id == user_id,
            JobModel.ended_on.is_(None),
            JobModel.archived.is_(False),
            JobModel.kind == JobKind.HOURLY.value,
            JobModel.hourly_rate.isnot(None),
            JobModel.hourly_rate > 0,
        )
        .order_by(JobModel.position, JobModel.name)
        .first()
    )
    if job is None:
        assumptions.append("No hourly job with a rate, so extra hours can't be priced.")
        return None

    rate = effective_rate(db, user_id, anchor - timedelta(days=DEDUCTION_LOOKBACK_DAYS), anchor, anchor)
    keep = 1 - rate.deduction_percent / 100 if rate.deduction_percent is not None else 1.0
    net_hourly = job.hourly_rate * keep * share
    weeks = (ends_on - anchor).days / 7
    shortfall = money(target - base_end)

    extra = None
    if shortfall > 0 and net_hourly > 0 and weeks > 0:
        # Rounded up to the half hour: a shift is not booked to the minute, and
        # rounding down would leave the target just out of reach.
        extra = math.ceil(shortfall / (net_hourly * weeks) * 2) / 2

    assumptions.append(
        f"Extra hours are priced at {job.name}'s {money_text(job.hourly_rate)} an hour"
        + (f", after {rate.deduction_percent:g}% deductions" if rate.deduction_percent is not None else "")
        + ", on top of the shifts already scheduled."
    )

    return Goal(
        target=money(target),
        target_on=ends_on,
        base_end_balance=base_end,
        shortfall=shortfall,
        job_name=job.name,
        net_hourly=money(net_hourly),
        weeks=round(weeks, 1),
        extra_hours_per_week=extra,
        scenarios=[
            Scenario(extra_hours_per_week=h, end_balance=money(base_end + h * weeks * net_hourly))
            for h in SCENARIO_HOURS
        ],
    )
