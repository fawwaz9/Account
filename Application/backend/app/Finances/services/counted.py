"""Which accounts count: one switch for net worth and every analytic (Phase 1 D39).

Its own module, depending only on the models, because every service that totals
money across accounts reads it -- account, budget, forecast, plan, tuition,
sinking funds, subscriptions -- and several of those import each other.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app._database.models import AccountModel, TransactionModel


def uncounted_accounts(user_id: uuid.UUID):
    """The ids of the accounts the student unticked, as a subquery (Phase 1 D39).

    One switch per account (`counts_toward_net_worth`) takes it out of net worth
    and every analytic -- safe to spend, the forecast, the year plan, spending
    summaries -- as if it did not exist. Recording is untouched: its ledger, its
    page, deposits into it. A subquery rather than a set, so a query that reads
    transactions adds one filter and no round trip.
    """
    return select(AccountModel.id).where(
        AccountModel.user_id == user_id,
        AccountModel.counts_toward_net_worth.is_(False),
    )


def on_counted_accounts(user_id: uuid.UUID):
    """A filter for TransactionModel queries: rows on accounts that count."""
    return TransactionModel.account_id.notin_(uncounted_accounts(user_id))


def uncounted_account_ids(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    """The same accounts as a set, for filtering rows already in Python."""
    return set(db.execute(uncounted_accounts(user_id)).scalars())
