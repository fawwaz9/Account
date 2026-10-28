"""Service functions for safe-to-spend: what can be spent before money next arrives.

A subtraction over figures the app already has: counted spending balances, the
standing instructions due before the next payday, and this month's sinking-fund
contributions not yet made. `safe_now` is the headline; `safe_soon` adds hourly
work done but not yet paid for and is never the headline.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app._database.models import AccountModel, JobModel
from app.Finances.schemas.safe import Commitment, SafeToSpend, SpendableAccount
from app.Finances.services.account_service import balances_by_account
from app.Finances.services.budget_service import month_bounds
from app.Finances.services.recurring_service import upcoming
from app.Finances.services.sinking_service import unfunded_total
from app.Jobs.services.earnings_service import upcoming_pay
from app.Jobs.services.job_service import next_pay_on
from app.Tasks.services.task_service import user_exists
from app.shared.dates import user_today
from app.shared.money import money
from app.Finances.services.counted import uncounted_account_ids

#: Account kinds whose balance is money you can spend.
#:
#: Per-account control is `counts_toward_net_worth` (Phase 1 D39): an unticked
#: spending account leaves this figure along with every other analytic.
SPENDABLE_KINDS = frozenset({"spending"})


def next_pay_date(db: Session, user_id: uuid.UUID, anchor: date) -> date | None:
    """Return the soonest pay date any of the user's jobs without an end date produces.

    Args:
        db: Open database session.
        user_id: Whose jobs.
        anchor: The day to look from, inclusive.

    Returns:
        The earliest next pay date; None when no job has a schedule.
    """
    jobs = (
        db.query(JobModel)
        .filter(JobModel.user_id == user_id, JobModel.ended_on.is_(None))
        .all()
    )
    dates = [d for d in (next_pay_on(job, anchor) for job in jobs) if d is not None]
    return min(dates) if dates else None


def window(db: Session, user_id: uuid.UUID, anchor: date) -> tuple[date, bool]:
    """Return the last day safe-to-spend must cover, and whether that is a real payday.

    Args:
        db: Open database session.
        user_id: Whose jobs.
        anchor: Today, on the user's clock.

    Returns:
        The day before the next pay date and True; or the month's end and False
        when no pay date falls after today.
    """
    payday = next_pay_date(db, user_id, anchor)
    if payday is not None and payday > anchor:
        return payday - timedelta(days=1), True

    _, month_end = month_bounds(anchor)
    # A payday today or in the past leaves nothing sensible to measure to, so
    # fall back rather than return a window that ends before it starts.
    return max(month_end, anchor), False


def spendable_accounts(db: Session, user_id: uuid.UUID) -> list[SpendableAccount]:
    """Return the user's counted, unarchived spending accounts with their balances.

    Args:
        db: Open database session.
        user_id: Whose accounts.

    Returns:
        The accounts in display order; empty when there are none.
    """
    accounts = (
        db.query(AccountModel)
        .filter(
            AccountModel.user_id == user_id,
            AccountModel.archived.is_(False),
            AccountModel.kind.in_(SPENDABLE_KINDS),
            AccountModel.counts_toward_net_worth.is_(True),
        )
        .all()
    )
    balances = balances_by_account(db, user_id)
    accounts.sort(key=lambda account: (account.position, account.name))

    return [
        SpendableAccount(
            account_id=account.id,
            name=account.name,
            balance=money(balances.get(account.id, 0.0)),
        )
        for account in accounts
    ]


def owed_for_work(db: Session, user_id: uuid.UUID, anchor: date) -> float:
    """Return the estimated pay for hourly shifts no cheque has covered yet.

    Salaried and contract jobs contribute nothing, since hours do not predict their
    pay.

    Args:
        db: Open database session.
        user_id: Whose jobs.
        anchor: Today, on the user's clock.

    Returns:
        The total in dollars, rounded to cents.
    """
    jobs = db.query(JobModel).filter(JobModel.user_id == user_id).all()
    rows = upcoming_pay(db, user_id, jobs, anchor)
    return money(sum(row.unpaid_estimate or 0.0 for row in rows))


def safe_to_spend(db: Session, user_id: uuid.UUID, on_day: date | None = None):
    """Return what the user can spend between today and the next payday.

    Commitments are the outgoing standing instructions (expenses and transfers)
    due in the window from any counted account; incoming ones are never counted.

    Args:
        db: Open database session.
        user_id: Whose money.
        on_day: The day to compute for; defaults to the user's today.

    Returns:
        The figures and their parts; None when the user does not exist.
    """
    if not user_exists(db, user_id):
        return None

    anchor = on_day or user_today(db, user_id)
    ends_on, until_payday = window(db, user_id, anchor)
    days = max(1, (ends_on - anchor).days + 1)

    accounts = spendable_accounts(db, user_id)
    spendable = money(sum(account.balance for account in accounts))

    charges = upcoming(db, user_id, anchor, ends_on) or []
    # Only money leaving. An incoming standing instruction inside the window is
    # money that has not arrived, and belongs in `safe_soon` at most -- counting
    # it here would be the optimism this figure exists to avoid.
    # A charge paid from an unticked account is no claim on what counts (D39).
    uncounted = uncounted_account_ids(db, user_id)
    leaving = [
        charge for charge in charges
        if charge.signed_amount < 0 and charge.account_id not in uncounted
    ]
    committed = money(sum(-charge.signed_amount for charge in leaving))

    # This month's sinking-fund contributions that are still promises. A
    # contribution already transferred needs nothing here: the money sits in a
    # savings account, which `spendable_accounts` already leaves out, and
    # subtracting it in both places would take it off twice.
    earmarked = unfunded_total(db, user_id, anchor)
    safe_now = money(spendable - committed - earmarked)
    owed = owed_for_work(db, user_id, anchor)

    return SafeToSpend(
        starts_on=anchor,
        ends_on=ends_on,
        days=days,
        until_payday=until_payday,
        spendable=spendable,
        committed=committed,
        earmarked=earmarked,
        safe_now=safe_now,
        owed_to_you=owed,
        safe_soon=money(safe_now + owed),
        # A daily allowance of minus four pounds is not guidance.
        per_day=money(safe_now / days) if safe_now > 0 else None,
        accounts=accounts,
        commitments=[
            Commitment(
                on_date=charge.on_date,
                description=charge.description,
                amount=money(-charge.signed_amount),
            )
            for charge in sorted(leaving, key=lambda c: c.on_date)
        ],
    )
