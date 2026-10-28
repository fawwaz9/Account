"""Service functions for deposits: income split across accounts by income share.

A deposit is one income row per receiving account, tied by one `group_id`. The
split divides by each account's share of the total shares, with the rounding
remainder on the largest share. `paycheque_service` reuses `split_income`.
"""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app._database.models import AccountModel, TransactionModel
from app.Finances.schemas.deposit import DepositAllocation, DepositCreate, DepositPreview
from app.Finances.schemas.transaction import TransactionKind
from app.Finances.services.transaction_service import as_schema


def active_accounts(db: Session, user_id: uuid.UUID) -> list[AccountModel]:
    """Return the user's unarchived accounts in their display order.

    Args:
        db: Open database session.
        user_id: Owner of the rows.

    Returns:
        Unarchived accounts ordered by `position`, then name.
    """
    accounts = (
        db.query(AccountModel)
        .filter(AccountModel.user_id == user_id, AccountModel.archived.is_(False))
        .all()
    )
    accounts.sort(key=lambda account: (account.position, account.name))
    return accounts


def split_income(amount: float, accounts: list[AccountModel]) -> list[DepositAllocation]:
    """Divide an amount across accounts by their income shares, to the cent.

    Args:
        amount: The deposit, in dollars.
        accounts: Candidate accounts; only those with a share above 0 take part.

    Returns:
        One allocation per sharing account, summing to `amount`, with the rounding
        remainder on the largest share; empty when no account has a share.
    """
    sharing = [account for account in accounts if account.income_share > 0]
    if not sharing:
        return []

    total_share = sum(account.income_share for account in sharing)
    allocations = [
        DepositAllocation(
            account_id=account.id,
            amount=round(amount * account.income_share / total_share, 2),
        )
        for account in sharing
    ]

    drift = round(amount - sum(entry.amount for entry in allocations), 2)
    if drift:
        biggest = max(
            range(len(sharing)), key=lambda index: sharing[index].income_share
        )
        allocations[biggest].amount = round(allocations[biggest].amount + drift, 2)

    return allocations


def preview_deposit(db: Session, user_id: uuid.UUID, amount: float):
    """Return how a deposit would split across the user's accounts, writing nothing.

    Args:
        db: Open database session.
        user_id: Whose accounts.
        amount: The deposit, in dollars.

    Returns:
        The split; `needs_shares` is True when no account has a share.
    """
    accounts = active_accounts(db, user_id)
    allocations = split_income(amount, accounts)
    return DepositPreview(
        amount=round(amount, 2),
        allocations=allocations,
        needs_shares=not allocations,
    )


def record_deposit(db: Session, user_id: uuid.UUID, data: DepositCreate):
    """Write a deposit as one income row per receiving account, in one commit.

    Uses the given allocations, or splits by income share; zero allocations write
    no row.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        data: The deposit and any explicit allocations.

    Returns:
        The rows written; None when an allocation names an account that is not
        one of the user's unarchived accounts.

    Raises:
        ValueError: If no allocations are given and no account has an income
            share.
    """
    accounts = active_accounts(db, user_id)
    by_id = {account.id: account for account in accounts}

    allocations = data.allocations or split_income(data.amount, accounts)
    if not allocations:
        raise ValueError(
            "No account has an income share yet. Set shares in your accounts, "
            "or choose the amounts for this deposit."
        )

    unknown = [entry.account_id for entry in allocations if entry.account_id not in by_id]
    if unknown:
        return None

    group_id = uuid.uuid4()
    rows = [
        TransactionModel(
            id=uuid.uuid4(),
            user_id=user_id,
            account_id=entry.account_id,
            kind=TransactionKind.INCOME.value,
            amount=entry.amount,
            description=data.description or "Deposit",
            occurred_on=data.occurred_on,
            group_id=group_id,
        )
        for entry in allocations
        if entry.amount > 0
    ]

    try:
        db.add_all(rows)
        db.commit()
    except Exception:
        db.rollback()
        raise

    for row in rows:
        db.refresh(row)
    return [as_schema(row) for row in rows]



