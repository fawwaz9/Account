"""Which accounts count: the one switch behind net worth and every money analytic.

An account with `counts_toward_net_worth` off is treated as absent by every
figure built from more than one account; its own ledger and page are untouched.
Kept in a module that depends only on the models, since the services reading it
import one another.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app._database.models import AccountModel, TransactionModel


def uncounted_accounts(user_id: uuid.UUID):
    """Return a subquery of the ids of the user's accounts that do not count.

    Args:
        user_id: Whose accounts.

    Returns:
        A SELECT of account ids, for use inside another query's filter.
    """
    return select(AccountModel.id).where(
        AccountModel.user_id == user_id,
        AccountModel.counts_toward_net_worth.is_(False),
    )


def on_counted_accounts(user_id: uuid.UUID):
    """Return a filter for transaction queries that keeps rows on accounts that count.

    Args:
        user_id: Whose accounts.

    Returns:
        A SQL expression for `TransactionModel` queries.
    """
    return TransactionModel.account_id.notin_(uncounted_accounts(user_id))


def uncounted_account_ids(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    """Return the ids of the user's accounts that do not count, as a set.

    Args:
        db: Open database session.
        user_id: Whose accounts.

    Returns:
        The account ids; empty when every account counts.
    """
    return set(db.execute(uncounted_accounts(user_id)).scalars())
