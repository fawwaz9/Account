import uuid
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app._database.models import (
    AccountModel,
    CourseModel,
    SpendCategoryModel,
    TransactionModel,
    TuitionDeductionModel,
    PaychequeModel,
    SinkingContributionModel,
    TuitionPaymentModel,
)
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


def owned_course(db: Session, user_id: uuid.UUID, course_id: uuid.UUID):
    """A course the caller owns, or None.

    Same reason as owned_category: the id arrives from the client, and one
    belonging to someone else would otherwise be stored happily.
    """
    return (
        db.query(CourseModel)
        .filter(CourseModel.id == course_id, CourseModel.user_id == user_id)
        .first()
    )


def tuition_payment_ids(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, uuid.UUID]:
    """transaction id -> tuition payment id, for the rows a tuition payment owns.

    One query for the whole ledger rather than one per row, the same way
    group_sizes works. The client needs it to send a tuition row to its own
    editor: editing the amount directly would leave the rate saying one thing
    and the ledger another.
    """
    rows = (
        db.query(TuitionPaymentModel.transaction_id, TuitionPaymentModel.id)
        .filter(TuitionPaymentModel.user_id == user_id)
        .all()
    )
    return {transaction_id: payment_id for transaction_id, payment_id in rows}


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


def as_schema(
    transaction: TransactionModel,
    group_size: int = 1,
    tuition_payment_id: uuid.UUID | None = None,
) -> Transaction:
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
        course_id=transaction.course_id,
        tuition_payment_id=tuition_payment_id,
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

    Raises for a window that cannot contain anything, and for an account that
    does not exist. Both used to answer `200 []`, which reads as "you have no
    transactions" -- the one answer that is certainly wrong, and the hardest
    kind of bug to notice on a money page.
    """
    if start is not None and end is not None and start > end:
        raise ValueError("The start of the range is after its end")

    query = db.query(TransactionModel).filter(TransactionModel.user_id == user_id)
    if account_id is not None:
        if owned_account(db, user_id, account_id) is None:
            raise LookupError("That account does not exist")
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
    tuition = tuition_payment_ids(db, user_id)
    return [
        as_schema(row, sizes.get(row.group_id, 1), tuition.get(row.id))
        for row in rows
    ]


def create_transaction(db: Session, user_id: uuid.UUID, data: TransactionCreate):
    if data.kind == TransactionKind.TRANSFER:
        raise ValueError("Use the transfer endpoint to move money between accounts")

    if owned_account(db, user_id, data.account_id) is None:
        return None

    if data.category_id is not None and owned_category(db, user_id, data.category_id) is None:
        raise ValueError("That category does not exist")

    if data.course_id is not None and owned_course(db, user_id, data.course_id) is None:
        raise ValueError("That course does not exist")

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
        # Same rule as the category: a course says what money went on, which
        # only makes sense for money going out.
        course_id=data.course_id if data.kind == TransactionKind.EXPENSE else None,
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

    # A tuition row's amount is derived: credits x rate, plus fees, less
    # deductions. Editing it here would leave the ledger saying one thing and the
    # course pages another, with nothing to say which was right -- so that edit
    # belongs in the tuition editor, which moves both together.
    if "amount" in update_data:
        owned_by_tuition = (
            db.query(TuitionPaymentModel)
            .filter(
                TuitionPaymentModel.user_id == user_id,
                TuitionPaymentModel.transaction_id == transaction_id,
            )
            .first()
        )
        if owned_by_tuition is not None:
            raise ValueError(
                "Edit this through Pay Tuition, so the per-credit rate and the "
                "amount stay in step"
            )

    course_id = update_data.get("course_id")
    if course_id is not None and owned_course(db, user_id, course_id) is None:
        raise ValueError("That course does not exist")

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

    # A tuition payment owns its ledger row, so removing the row must remove the
    # record of what it was for. Left behind, the payment row still answered
    # "what did this course cost" for a payment that no longer exists, and
    # nothing in the UI could reach it to clear it.
    doomed_payments = (
        db.query(TuitionPaymentModel)
        .filter(
            TuitionPaymentModel.user_id == user_id,
            TuitionPaymentModel.transaction_id == transaction.id,
        )
        .all()
    )
    for payment in doomed_payments:
        db.query(TuitionDeductionModel).filter(
            TuitionDeductionModel.tuition_payment_id == payment.id
        ).delete(synchronize_session=False)
        db.delete(payment)

    # A paycheque owns the rows its net was split into, so removing them must
    # remove the cheque as well. Left behind it would still answer "what did
    # this job pay" for money no longer recorded anywhere -- the orphaned
    # tuition payment, again. Matched on group_id because a cheque is several
    # rows, not one.
    if transaction.group_id is not None:
        doomed_cheques = (
            db.query(PaychequeModel)
            .filter(
                PaychequeModel.user_id == user_id,
                PaychequeModel.group_id == transaction.group_id,
            )
            .all()
        )
        # Deductions follow through the relationship's delete-orphan cascade.
        for cheque in doomed_cheques:
            db.delete(cheque)

        # A sinking-fund contribution owns the transfer it wrote, so removing
        # the transfer must remove the contribution -- otherwise the fund goes
        # on claiming money that is no longer set aside anywhere.
        db.query(SinkingContributionModel).filter(
            SinkingContributionModel.group_id == transaction.group_id
        ).delete(synchronize_session=False)

    if transaction.group_id is not None and (is_transfer or scope == "group"):
        db.query(TransactionModel).filter(
            TransactionModel.group_id == transaction.group_id,
            TransactionModel.user_id == user_id,
        ).delete(synchronize_session=False)
    else:
        db.delete(transaction)

    db.commit()
    return removed
