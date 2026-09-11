import uuid
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app._database.models import AccountModel, SpendCategoryModel, TransactionModel
from app.Finances.schemas.transaction import (
    Transaction,
    TransactionCreate,
    TransactionKind,
    TransactionUpdate,
    TransferCreate,
)


def owned_account(db: Session, user_id: uuid.UUID, account_id: uuid.UUID):
    return (
        db.query(AccountModel)
        .filter(AccountModel.id == account_id, AccountModel.user_id == user_id)
        .first()
    )


def owned_category(db: Session, user_id: uuid.UUID, category_id: uuid.UUID):
    """A category the caller owns, or None.

    Checked on every write: category_id arrives from the client, and an id
    belonging to someone else would otherwise be stored happily.
    """
    return (
        db.query(SpendCategoryModel)
        .filter(SpendCategoryModel.id == category_id, SpendCategoryModel.user_id == user_id)
        .first()
    )


def group_sizes(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """How many rows share each group, in one grouped query rather than one per row."""
    rows = (
        db.query(TransactionModel.group_id, func.count(TransactionModel.id))
        .filter(TransactionModel.user_id == user_id, TransactionModel.group_id.isnot(None))
        .group_by(TransactionModel.group_id)
        .all()
    )
    return {group_id: count for group_id, count in rows}


def signed(kind: TransactionKind, amount: float) -> float:
    """Money in is positive, money out is negative.

    Applied here rather than trusted from the caller, so an expense cannot be
    recorded in a way that raises a balance.
    """
    return amount if kind == TransactionKind.INCOME else -amount


def as_schema(transaction: TransactionModel, group_size: int = 1) -> Transaction:
    """Build the API shape without touching the mapped instance.

    An earlier version flipped transaction.amount to its magnitude for display,
    which marked the row dirty. A delete in the same session then removed it
    while that UPDATE was still pending, and the flush raised StaleDataError.
    Returning a detached snapshot also means a deleted row can still be
    serialized back to the caller.
    """
    return Transaction(
        id=transaction.id,
        kind=transaction.kind,
        account_id=transaction.account_id,
        amount=abs(transaction.amount),
        signed_amount=transaction.amount,
        description=transaction.description,
        occurred_on=transaction.occurred_on,
        group_id=transaction.group_id,
        group_size=group_size,
        category_id=transaction.category_id,
    )


def list_transactions(
    db: Session,
    user_id: uuid.UUID,
    account_id: uuid.UUID | None = None,
    limit: int = 100,
    start: date | None = None,
    end: date | None = None,
):
    """The account holder's movements, newest first, optionally windowed.

    `limit` truncates the *oldest* rows, because the ordering is newest-first.
    A caller that wants a specific stretch of time must therefore narrow with
    `start`/`end` rather than fetch a page and filter it, or the rows it drops
    are silently the ones furthest back.
    """
    query = db.query(TransactionModel).filter(TransactionModel.user_id == user_id)
    if account_id is not None:
        query = query.filter(TransactionModel.account_id == account_id)
    if start is not None:
        query = query.filter(TransactionModel.occurred_on >= start)
    if end is not None:
        query = query.filter(TransactionModel.occurred_on <= end)

    rows = (
        query.order_by(TransactionModel.occurred_on.desc(), TransactionModel.id.desc())
        .limit(limit)
        .all()
    )
    sizes = group_sizes(db, user_id)
    return [as_schema(row, sizes.get(row.group_id, 1)) for row in rows]


def create_transaction(db: Session, user_id: uuid.UUID, data: TransactionCreate):
    if data.kind == TransactionKind.TRANSFER:
        raise ValueError("Use the transfer endpoint to move money between accounts")

    if owned_account(db, user_id, data.account_id) is None:
        return None

    if data.category_id is not None and owned_category(db, user_id, data.category_id) is None:
        raise ValueError("That category does not exist")

    transaction = TransactionModel(
        id=uuid.uuid4(),
        user_id=user_id,
        account_id=data.account_id,
        kind=data.kind.value,
        amount=signed(data.kind, data.amount),
        description=data.description,
        occurred_on=data.occurred_on,
        # A category labels what money went on, which only makes sense for
        # money going out.
        category_id=data.category_id if data.kind == TransactionKind.EXPENSE else None,
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return as_schema(transaction)


def create_transfer(db: Session, user_id: uuid.UUID, data: TransferCreate):
    """Two rows sharing a group_id: one out of the source, one into the target.

    Written in a single commit so a transfer can never exist as half of itself.
    """
    source = owned_account(db, user_id, data.from_account_id)
    target = owned_account(db, user_id, data.to_account_id)
    if source is None or target is None:
        return None

    group_id = uuid.uuid4()
    description = data.description or f"{source.name} to {target.name}"

    halves = [
        TransactionModel(
            id=uuid.uuid4(),
            user_id=user_id,
            account_id=account.id,
            kind=TransactionKind.TRANSFER.value,
            amount=amount,
            description=description,
            occurred_on=data.occurred_on,
            group_id=group_id,
        )
        for account, amount in ((source, -data.amount), (target, data.amount))
    ]

    try:
        db.add_all(halves)
        db.commit()
    except Exception:
        db.rollback()
        raise

    for half in halves:
        db.refresh(half)
    return [as_schema(half) for half in halves]


def get_transaction(db: Session, user_id: uuid.UUID, transaction_id: uuid.UUID):
    transaction = (
        db.query(TransactionModel)
        .filter(TransactionModel.id == transaction_id, TransactionModel.user_id == user_id)
        .first()
    )
    if transaction is None:
        return None

    size = 1
    if transaction.group_id is not None:
        size = (
            db.query(func.count(TransactionModel.id))
            .filter(
                TransactionModel.group_id == transaction.group_id,
                TransactionModel.user_id == user_id,
            )
            .scalar()
            or 1
        )

    return as_schema(transaction, size)


def update_transaction(
    db: Session, user_id: uuid.UUID, transaction_id: uuid.UUID, data: TransactionUpdate
):
    transaction = (
        db.query(TransactionModel)
        .filter(TransactionModel.id == transaction_id, TransactionModel.user_id == user_id)
        .first()
    )
    if transaction is None:
        return None

    update_data = data.model_dump(exclude_unset=True)

    category_id = update_data.get("category_id")
    if category_id is not None and owned_category(db, user_id, category_id) is None:
        raise ValueError("That category does not exist")

    new_amount = update_data.pop("amount", None)

    for key, value in update_data.items():
        setattr(transaction, key, value)

    if new_amount is not None:
        # Keep the existing direction: editing an expense to 40 must not turn
        # it into income.
        direction = 1 if transaction.amount >= 0 else -1
        transaction.amount = direction * new_amount

    # Only a transfer has a partner to keep in step, and it must be kept in step
    # for every field -- moving one leg's date and not the other puts the two
    # halves in different months. A deposit's legs share a group_id too, but they
    # are independent income rows: mirroring an amount onto one would negate it
    # into negative income, a state nothing downstream can represent.
    if transaction.group_id is not None and transaction.kind == TransactionKind.TRANSFER.value:
        partner = (
            db.query(TransactionModel)
            .filter(
                TransactionModel.group_id == transaction.group_id,
                TransactionModel.user_id == user_id,
                TransactionModel.id != transaction.id,
            )
            .first()
        )
        if partner is not None:
            if new_amount is not None:
                partner.amount = -transaction.amount
            if "occurred_on" in update_data:
                partner.occurred_on = transaction.occurred_on
            if "description" in update_data:
                partner.description = transaction.description

    db.commit()
    db.refresh(transaction)
    return as_schema(transaction)


def delete_transaction(
    db: Session,
    user_id: uuid.UUID,
    transaction_id: uuid.UUID,
    scope: str = "group",
):
    """Remove one row, or the whole group it belongs to.

    A transfer is always removed whole and ignores `scope` -- half a transfer is
    not a thing. A deposit's allocations share a group_id as well, but each is an
    independent income row, so there the caller decides: "row" drops one
    allocation, "group" drops the deposit. Defaulting to "group" keeps the
    behaviour every existing caller already relies on.
    """
    transaction = (
        db.query(TransactionModel)
        .filter(TransactionModel.id == transaction_id, TransactionModel.user_id == user_id)
        .first()
    )
    if transaction is None:
        return None

    removed = as_schema(transaction)
    is_transfer = transaction.kind == TransactionKind.TRANSFER.value

    if transaction.group_id is not None and (is_transfer or scope == "group"):
        db.query(TransactionModel).filter(
            TransactionModel.group_id == transaction.group_id,
            TransactionModel.user_id == user_id,
        ).delete(synchronize_session=False)
    else:
        db.delete(transaction)

    db.commit()
    return removed
