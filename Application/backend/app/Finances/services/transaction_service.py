import uuid

from sqlalchemy.orm import Session

from app._database.models import AccountModel, TransactionModel
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


def signed(kind: TransactionKind, amount: float) -> float:
    """Money in is positive, money out is negative.

    Applied here rather than trusted from the caller, so an expense cannot be
    recorded in a way that raises a balance.
    """
    return amount if kind == TransactionKind.INCOME else -amount


def as_schema(transaction: TransactionModel) -> Transaction:
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
        category_id=transaction.category_id,
    )


def list_transactions(
    db: Session,
    user_id: uuid.UUID,
    account_id: uuid.UUID | None = None,
    limit: int = 100,
):
    query = db.query(TransactionModel).filter(TransactionModel.user_id == user_id)
    if account_id is not None:
        query = query.filter(TransactionModel.account_id == account_id)

    rows = (
        query.order_by(TransactionModel.occurred_on.desc(), TransactionModel.id.desc())
        .limit(limit)
        .all()
    )
    return [as_schema(row) for row in rows]


def create_transaction(db: Session, user_id: uuid.UUID, data: TransactionCreate):
    if data.kind == TransactionKind.TRANSFER:
        raise ValueError("Use the transfer endpoint to move money between accounts")

    if owned_account(db, user_id, data.account_id) is None:
        return None

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
    return None if transaction is None else as_schema(transaction)


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
    new_amount = update_data.pop("amount", None)

    for key, value in update_data.items():
        setattr(transaction, key, value)

    if new_amount is not None:
        # Keep the existing direction: editing an expense to 40 must not turn
        # it into income. Both halves of a transfer move together.
        direction = 1 if transaction.amount >= 0 else -1
        transaction.amount = direction * new_amount

        if transaction.group_id is not None:
            partner = (
                db.query(TransactionModel)
                .filter(
                    TransactionModel.group_id == transaction.group_id,
                    TransactionModel.id != transaction.id,
                )
                .first()
            )
            if partner is not None:
                partner.amount = -transaction.amount
                if "occurred_on" in update_data:
                    partner.occurred_on = transaction.occurred_on
                if "description" in update_data:
                    partner.description = transaction.description

    db.commit()
    db.refresh(transaction)
    return as_schema(transaction)


def delete_transaction(db: Session, user_id: uuid.UUID, transaction_id: uuid.UUID):
    """Deletes both halves of a transfer -- half a transfer is not a thing."""
    transaction = (
        db.query(TransactionModel)
        .filter(TransactionModel.id == transaction_id, TransactionModel.user_id == user_id)
        .first()
    )
    if transaction is None:
        return None

    removed = as_schema(transaction)
    if transaction.group_id is not None:
        db.query(TransactionModel).filter(
            TransactionModel.group_id == transaction.group_id,
            TransactionModel.user_id == user_id,
        ).delete(synchronize_session=False)
    else:
        db.delete(transaction)

    db.commit()
    return removed
