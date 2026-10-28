"""Service functions for the cash-flow forecast: balance ahead, runway and run-rates.

Arithmetic over figures the app already holds, from today to the term's end:
spending balances as safe-to-spend counts them, standing instructions as
`/recurring/upcoming` projects them, pay from each current job's pay dates (net
of the deduction rate recent cheques show, at the spending accounts' share of
the income split), and day-to-day spending at the recent one-off pace. Every
response lists what it assumed. `plan_service` reuses the pieces.
"""

import re
import uuid
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app._database.models import (
    AccountModel,
    JobModel,
    TransactionModel,
    TuitionPaymentModel,
    UserModel,
)
from app.Finances.schemas.forecast import (
    CashFlowForecast,
    ForecastEvent,
    ForecastPoint,
    MerchantRunRate,
    Runway,
)
from app.Finances.services.account_service import balances_by_account
from app.Finances.services.recurring_service import upcoming
from app.Finances.services.safe_service import spendable_accounts
from app.Grades.utils.terms import term_dates
from app.Jobs.schemas.job import JobKind
from app.Jobs.services.earnings_service import (
    earned_from_shifts,
    effective_rate,
    upcoming_pay,
)
from app.Jobs.services.job_service import list_shifts
from app.Jobs.services.pay_schedule import pay_dates as job_pay_dates
from app.shared.dates import user_today
from app.shared.money import money
from app.Finances.services.counted import on_counted_accounts

#: How far back "recent" spending reaches. Eight weeks: long enough that one
#: big weekend does not set the pace for a term, short enough to follow a
#: change of habit within the same term.
LOOKBACK_DAYS = 56
#: The horizon when the current term's end is not known.
FALLBACK_DAYS = 16 * 7
#: Never project further than the recurring engine will (it refuses past 400).
MAX_DAYS = 400
#: How far back cheques are read to learn a deduction rate.
DEDUCTION_LOOKBACK_DAYS = 180
#: Account kinds whose balance counts toward runway.
LIQUID_KINDS = frozenset({"spending", "savings", "emergency"})
#: How many merchants the run-rate list names.
RUN_RATE_LIMIT = 5
#: A merchant needs this many one-off purchases before it has a pace at all.
RUN_RATE_MIN_OCCURRENCES = 2


def forecast(db: Session, user_id: uuid.UUID, on_day: date | None = None) -> CashFlowForecast | None:
    """Return the forecast for the user's counted spending accounts.

    Args:
        db: Open database session.
        user_id: Whose money.
        on_day: The day to forecast from; defaults to the user's today.

    Returns:
        The daily balances, the dated events, when the balance first goes below
        zero, its lowest point, runway, run-rates and the assumptions; None when
        the user does not exist.

    Raises:
        ValueError: If the recurring projection refuses the window.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None

    anchor = on_day or user_today(db, user_id)
    ends_on, at_term_end = horizon(user, anchor)
    assumptions: list[str] = []
    if not at_term_end:
        assumptions.append(
            "Your current term's dates aren't known, so this looks 16 weeks ahead."
        )

    accounts = spendable_accounts(db, user_id)
    spendable_ids = {account.account_id for account in accounts}
    starting = money(sum(account.balance for account in accounts))

    excluded = tuition_transaction_ids(db, user_id)
    history_days = days_of_history(db, user_id, anchor)
    paying_from = spendable_ids | debt_account_ids(db, user_id)
    daily = daily_one_off_spending(db, user_id, paying_from, anchor, history_days, excluded)
    if history_days == 0:
        assumptions.append("No spending history yet, so day-to-day spending is counted as $0.")
    else:
        assumptions.append(
            f"Day-to-day spending continues at {money_text(daily)} a day, the average of "
            f"one-off spending over the last {history_days} days "
            "(standing instructions and tuition are counted separately; card purchases count "
            "as they happen, since your spending accounts pay the card)."
        )
        if history_days < 14:
            assumptions.append(
                f"That average rests on only {history_days} days of history, so it will move."
            )

    raw_share = spendable_income_share(db, user_id, spendable_ids)
    share = 1.0 if raw_share is None else raw_share
    events = recurring_events(db, user_id, spendable_ids, anchor, ends_on, share)
    if events:
        assumptions.append("Standing instructions run as scheduled.")
    events += pay_events(db, user_id, spendable_ids, anchor, ends_on, share, assumptions)
    if any(event.split for event in events) and (raw_share is None or raw_share < 1):
        assumptions.append(income_share_note(raw_share))
    events.sort(key=lambda event: (event.on_date, event.source, event.description))
    assumptions.append(
        "Tuition instalments, and anything else not yet recorded or scheduled, aren't included."
    )

    points, negative_on, lowest, lowest_on = project(starting, daily, events, anchor, ends_on)

    return CashFlowForecast(
        starts_on=anchor,
        ends_on=ends_on,
        ends_at_term_end=at_term_end,
        starting_balance=starting,
        daily_spending=daily,
        spending_history_days=history_days,
        points=points,
        events=events,
        negative_on=negative_on,
        lowest_balance=lowest,
        lowest_on=lowest_on,
        ending_balance=points[-1].balance,
        runway=runway(db, user_id, anchor, history_days, assumptions),
        run_rates=run_rates(db, user_id, anchor, ends_on, history_days, excluded),
        assumptions=assumptions,
    )


# --- the horizon and the history ------------------------------------------

def horizon(user: UserModel, anchor: date) -> tuple[date, bool]:
    """Return the forecast's end: the current term's last day, or 16 weeks out.

    The term's end is used only when it falls between a week and `MAX_DAYS` ahead.

    Args:
        user: The user, for their term and first-year anchor.
        anchor: Today.

    Returns:
        The end date and whether it is the term's end.
    """
    span = term_dates(user.current_semester, user.current_school_year, user.first_year_calendar_year)
    if span is not None:
        _, term_end = span
        if anchor + timedelta(days=7) <= term_end <= anchor + timedelta(days=MAX_DAYS):
            return term_end, True
    return anchor + timedelta(days=FALLBACK_DAYS), False


def days_of_history(db: Session, user_id: uuid.UUID, anchor: date) -> int:
    """Return how many days of the 56-day look-back the user's ledger actually covers.

    Counted from the earliest row before today on a counted account, so a new
    ledger's pace is not understated by dividing by 56.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        anchor: Today.

    Returns:
        0 to `LOOKBACK_DAYS`; 0 when there is no history.
    """
    first = (
        db.query(TransactionModel.occurred_on)
        .filter(
            TransactionModel.user_id == user_id,
            TransactionModel.occurred_on < anchor,
            on_counted_accounts(user_id),
        )
        .order_by(TransactionModel.occurred_on.asc())
        .first()
    )
    if first is None:
        return 0
    return max(0, min(LOOKBACK_DAYS, (anchor - first.occurred_on).days))


def debt_account_ids(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    """Return the ids of the user's counted, unarchived debt accounts.

    Args:
        db: Open database session.
        user_id: Owner of the rows.

    Returns:
        Ids of the matching accounts; empty when there are none.
    """
    rows = (
        db.query(AccountModel.id)
        .filter(AccountModel.user_id == user_id, AccountModel.archived.is_(False),
                AccountModel.kind == "debt", AccountModel.counts_toward_net_worth.is_(True))
        .all()
    )
    return {row.id for row in rows}


def tuition_transaction_ids(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    """Return the ids of the ledger rows that tuition payments own.

    Args:
        db: Open database session.
        user_id: Owner of the rows.

    Returns:
        Transaction ids owned by a tuition payment.
    """
    rows = (
        db.query(TuitionPaymentModel.transaction_id)
        .filter(TuitionPaymentModel.user_id == user_id)
        .all()
    )
    return {row.transaction_id for row in rows}


def one_off_expenses(
    db: Session,
    user_id: uuid.UUID,
    anchor: date,
    history_days: int,
    excluded: set[uuid.UUID],
    account_ids: set[uuid.UUID] | None = None,
) -> list[TransactionModel]:
    """Return recent expenses with no standing instruction behind them and no tuition.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        anchor: Today; rows from before today count.
        history_days: How far back to look.
        excluded: Row ids to leave out (tuition).
        account_ids: Only these accounts; None for every counted account.

    Returns:
        The expense rows; empty with no history or an empty account set.
    """
    if history_days == 0:
        return []
    query = db.query(TransactionModel).filter(
        TransactionModel.user_id == user_id,
        TransactionModel.kind == "expense",
        TransactionModel.recurring_id.is_(None),
        TransactionModel.occurred_on >= anchor - timedelta(days=history_days),
        TransactionModel.occurred_on < anchor,
    )
    if account_ids is not None:
        if not account_ids:
            return []
        query = query.filter(TransactionModel.account_id.in_(account_ids))
    else:
        query = query.filter(on_counted_accounts(user_id))  # every account that counts (D39)
    return [row for row in query.all() if row.id not in excluded]


def daily_one_off_spending(
    db: Session,
    user_id: uuid.UUID,
    spendable_ids: set[uuid.UUID],
    anchor: date,
    history_days: int,
    excluded: set[uuid.UUID],
) -> float:
    """Return the average one-off spending per day over the look-back, never negative.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        spendable_ids: Accounts to read (spending and debt).
        anchor: Today.
        history_days: Days the average is taken over.
        excluded: Row ids to leave out (tuition).

    Returns:
        Dollars per day, rounded to cents; 0 with no history.
    """
    rows = one_off_expenses(db, user_id, anchor, history_days, excluded, spendable_ids)
    if not rows:
        return 0.0
    # Expenses are stored negative. A refund recorded as a positive expense
    # lowers the total, as it should, but the pace never goes below zero.
    spent = -sum(row.amount for row in rows)
    return money(max(0.0, spent) / history_days)


# --- what is scheduled -----------------------------------------------------

def recurring_events(
    db: Session,
    user_id: uuid.UUID,
    spendable_ids: set[uuid.UUID],
    start: date,
    end: date,
    share: float,
) -> list[ForecastEvent]:
    """Turn the standing instructions due in a window into events on the given accounts.

    An expense or income counts when its account is in the set; a transfer counts by
    its net effect on the set; a deposit counts at `share`.

    Args:
        db: Open database session.
        user_id: Whose instructions.
        spendable_ids: The accounts being forecast.
        start: First date, inclusive.
        end: Last date, inclusive.
        share: The fraction of a deposit that lands in those accounts.

    Returns:
        The events, skipping any that leave the set unchanged.
    """
    events: list[ForecastEvent] = []
    for charge in upcoming(db, user_id, start, end) or []:
        if charge.kind == "deposit":
            # Names no account: it splits by income share when it runs.
            delta = charge.amount * share
        elif charge.kind == "transfer":
            delta = 0.0
            if charge.account_id in spendable_ids:
                delta -= charge.amount
            if charge.to_account_id in spendable_ids:
                delta += charge.amount
        elif charge.account_id in spendable_ids:
            delta = charge.signed_amount
        else:
            delta = 0.0
        if delta == 0:
            continue
        events.append(ForecastEvent(
            on_date=charge.on_date,
            description=charge.description or charge.kind.capitalize(),
            amount=money(delta),
            source="recurring",
            split=charge.kind == "deposit",
        ))
    return events


def pay_dates(job: JobModel, start: date, end: date) -> list[date]:
    """Return a job's pay dates in a window, by whichever schedule it has.

    Args:
        job: The job whose pay schedule to read.
        start: First day of the window, inclusive.
        end: Last day of the window, inclusive.

    Returns:
        Pay dates in the window, from `pay_schedule.pay_dates`.
    """
    return job_pay_dates(job, start, end)


def spendable_income_share(db: Session, user_id: uuid.UUID, spendable_ids: set[uuid.UUID]) -> float | None:
    """Return the fraction of incoming money the income split sends to some accounts.

    Args:
        db: Open database session.
        user_id: Whose accounts.
        spendable_ids: The accounts whose share is wanted.

    Returns:
        Their shares over the total of every unarchived account's share; None
        when no account has a share.
    """
    accounts = (
        db.query(AccountModel)
        .filter(AccountModel.user_id == user_id, AccountModel.archived.is_(False))
        .all()
    )
    sharing = [account for account in accounts if account.income_share > 0]
    total = sum(account.income_share for account in sharing)
    if total <= 0:
        return None
    return sum(a.income_share for a in sharing if a.id in spendable_ids) / total


def income_share_note(share: float | None) -> str:
    """Return the assumption sentence about where pay and deposits land.

    Args:
        share: Fraction of income that lands in spending accounts, 0-1; None when no
            split is set.

    Returns:
        The sentence to list among the forecast's assumptions.
    """
    if share is None:
        return "No income split is set, so pay and deposits are assumed to land in your spending accounts."
    return (
        f"Pay and deposits count at the {round(share * 100)}% your income split sends to "
        "spending accounts."
    )


def pay_events(
    db: Session,
    user_id: uuid.UUID,
    spendable_ids: set[uuid.UUID],
    anchor: date,
    end: date,
    share: float,
    assumptions: list[str],
) -> list[ForecastEvent]:
    """Return the pay each current job is expected to bring in a window.

    Pay dates come from each unended, unarchived job's schedule, from tomorrow. An
    hourly cheque pays the scheduled shifts since the previous pay date (the first
    also carries work no cheque has covered); a salaried one pays its period amount;
    contract jobs are not predicted. Amounts are taken after the recent deduction
    rate and scaled by `share`. Notes are appended to `assumptions`.

    Args:
        db: Open database session.
        user_id: Whose jobs.
        spendable_ids: The accounts being forecast.
        anchor: Today.
        end: Last date, inclusive.
        share: The fraction of pay that lands in those accounts.
        assumptions: The list to add assumption sentences to.

    Returns:
        The pay events; empty when there are no current jobs.
    """
    jobs = (
        db.query(JobModel)
        .filter(JobModel.user_id == user_id, JobModel.ended_on.is_(None), JobModel.archived.is_(False))
        .order_by(JobModel.position, JobModel.name)
        .all()
    )
    if not jobs:
        return []

    rate = effective_rate(db, user_id, anchor - timedelta(days=DEDUCTION_LOOKBACK_DAYS), anchor, anchor)
    if rate.deduction_percent is not None:
        keep = 1 - rate.deduction_percent / 100
        assumptions.append(
            f"Pay is taken after {rate.deduction_percent:g}% deductions, the rate your recent cheques show."
        )
    else:
        keep = 1.0

    unpaid = {row.job_id: row.unpaid_estimate or 0.0 for row in upcoming_pay(db, user_id, jobs, anchor)}
    future_shifts = list_shifts(db, user_id, anchor + timedelta(days=1), end, on_day=anchor) or []

    events: list[ForecastEvent] = []
    gross_used = False
    for job in jobs:
        # From tomorrow: a cheque due today may already be recorded, and counting
        # it again would be the optimism this exists to avoid.
        dates = pay_dates(job, anchor + timedelta(days=1), end)
        if not dates:
            if job.kind != JobKind.CONTRACT.value:
                assumptions.append(f"{job.name} has no pay schedule, so its pay isn't included.")
            continue
        if job.kind == JobKind.CONTRACT.value:
            assumptions.append(f"{job.name} is contract work, paid as invoiced, so it isn't predicted.")
            continue

        mine = [shift for shift in future_shifts if shift.job_id == job.id]
        previous = anchor
        for index, payday in enumerate(dates):
            if job.kind == JobKind.SALARIED.value:
                gross = job.period_amount or 0.0
            else:
                # Shifts after the previous pay date up to this one. The first
                # cheque also carries the work no cheque has covered yet.
                bucket = [s for s in mine if previous < s.on_date <= payday]
                gross, _ = earned_from_shifts(job, bucket)
                if index == 0:
                    gross += unpaid.get(job.id, 0.0)
            previous = payday
            if gross <= 0:
                continue
            gross_used = True
            amount = money(gross * keep * share)
            if amount <= 0:
                continue
            events.append(ForecastEvent(
                on_date=payday, description=f"Pay: {job.name}", amount=amount, source="pay",
                split=True,
            ))

    if gross_used:
        assumptions.append(
            "Hourly pay is for your scheduled shifts, paid on the next pay date after each "
            "(real payrolls often lag a period, so a cheque may land later)."
        )
        if rate.deduction_percent is None:
            assumptions.append(
                "Pay is counted before deductions: no recorded cheques yet to learn them from."
            )
    return events


# --- the projection --------------------------------------------------------

def project(
    starting: float, daily: float, events: list[ForecastEvent], start: date, end: date,
) -> tuple[list[ForecastPoint], date | None, float, date]:
    """Walk the balance day by day from today to the end of the window.

    Today keeps what was already spent; daily spending starts tomorrow. Events land
    on their dates.

    Args:
        starting: Today's balance.
        daily: Spending per day from tomorrow.
        events: Dated movements, signed.
        start: Today.
        end: The last day, inclusive.

    Returns:
        The daily points, the first day below zero (or None), the lowest balance
        and its day.
    """
    by_day: dict[date, float] = defaultdict(float)
    for event in events:
        by_day[event.on_date] += event.amount

    balance = starting
    points: list[ForecastPoint] = []
    negative_on: date | None = None
    lowest, lowest_on = None, start
    day = start
    while day <= end:
        if day > start:
            balance -= daily
        balance += by_day.get(day, 0.0)
        rounded = money(balance)
        points.append(ForecastPoint(on_date=day, balance=rounded))
        if negative_on is None and rounded < 0:
            negative_on = day
        if lowest is None or rounded < lowest:
            lowest, lowest_on = rounded, day
        day += timedelta(days=1)
    return points, negative_on, lowest, lowest_on


# --- runway and run-rates --------------------------------------------------

def runway(
    db: Session, user_id: uuid.UUID, anchor: date, history_days: int, assumptions: list[str],
) -> Runway | None:
    """Return how long liquid money lasts at the recent net pace of money in and out.

    Every income and expense on counted accounts over the look-back counts, rent
    and tuition included; transfers burn nothing. Adds its assumption sentence.

    Args:
        db: Open database session.
        user_id: Whose money.
        anchor: Today.
        history_days: Days of history to average over.
        assumptions: The list to add the assumption sentence to.

    Returns:
        The liquid balance, the daily burn and the day it runs out; None with no
        history.
    """
    if history_days == 0:
        return None

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
    liquid = money(sum(balances.get(account.id, 0.0) for account in accounts))

    rows = (
        db.query(TransactionModel.amount)
        .filter(
            TransactionModel.user_id == user_id,
            TransactionModel.kind.in_(("income", "expense")),
            TransactionModel.occurred_on >= anchor - timedelta(days=history_days),
            TransactionModel.occurred_on < anchor,
            on_counted_accounts(user_id),
        )
        .all()
    )
    net_per_day = sum(row.amount for row in rows) / history_days
    burn = money(-net_per_day) if net_per_day < 0 else 0.0

    lasts_until = None
    if burn > 0 and liquid > 0:
        lasts_until = anchor + timedelta(days=int(liquid // burn))
    assumptions.append(
        f"Runway divides spending, savings and emergency balances by the last {history_days} days' "
        "average of all money in and out, rent and tuition included."
    )
    return Runway(liquid=liquid, daily_burn=burn, lasts_until=lasts_until)


_NOISE = re.compile(r"[\d#*]+")
_SPACES = re.compile(r"\s+")


def merchant_key(description: str | None) -> str:
    """Normalise a description into a merchant key, dropping digits, # and *.

    "Subway #1234" and "SUBWAY 0042" give the same key; None or empty gives "".

    Args:
        description: A transaction description; may be None.

    Returns:
        The lower-cased key, or "" for an empty description.
    """
    if not description:
        return ""
    return _SPACES.sub(" ", _NOISE.sub(" ", description.lower())).strip(" -.,")


def run_rates(
    db: Session,
    user_id: uuid.UUID,
    anchor: date,
    ends_on: date,
    history_days: int,
    excluded: set[uuid.UUID],
) -> list[MerchantRunRate]:
    """Return the merchants taking the most one-off spending, carried to the horizon.

    Every counted account counts, cards included. A merchant needs at least two
    purchases in the look-back.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        anchor: Today.
        ends_on: The forecast's horizon.
        history_days: Days of history the pace is taken over.
        excluded: Row ids to leave out (tuition).

    Returns:
        Up to five merchants, by projected spending.
    """
    rows = one_off_expenses(db, user_id, anchor, history_days, excluded)
    groups: dict[str, list[TransactionModel]] = defaultdict(list)
    for row in rows:
        key = merchant_key(row.description)
        if key:
            groups[key].append(row)

    remaining = (ends_on - anchor).days
    found: list[MerchantRunRate] = []
    for items in groups.values():
        if len(items) < RUN_RATE_MIN_OCCURRENCES:
            continue
        spent = -sum(item.amount for item in items)
        if spent <= 0:
            continue
        label = sorted(items, key=lambda item: item.occurred_on)[-1].description.strip()
        found.append(MerchantRunRate(
            merchant=label,
            spent=money(spent),
            occurrences=len(items),
            projected=money(spent / history_days * remaining),
        ))
    found.sort(key=lambda rate: (-rate.projected, rate.merchant.lower()))
    return found[:RUN_RATE_LIMIT]


def money_text(amount: float) -> str:
    """Format dollars for a sentence, such as "$1,234.50".

    Args:
        amount: Dollars.

    Returns:
        The amount with a dollar sign, thousands separators and cents.
    """
    return f"${amount:,.2f}"
