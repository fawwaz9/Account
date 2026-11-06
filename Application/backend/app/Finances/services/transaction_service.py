"""Service functions for the ledger: income, expenses and transfers.

A balance is the sum of an account's rows, so amounts are stored signed:
positive into the account, negative out. A transfer is two rows tied by a
`group_id`, written and edited together. Rows owned by a tuition payment, a
paycheque or a sinking contribution take their owner with them when deleted.
"""

import uuid
from datetime import date

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app._database.models import (
    AccountModel,
    CourseModel,
    SpendCategoryModel,
    TransactionModel,
    TuitionDeductionModel,
    PaychequeModel,
    RecurringTransactionModel,
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
    """Return the user's account with this id, or None.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        account_id: The account to fetch.

    Returns:
        The account, or None when it is missing or another user's.
    """
    return (
        db.query(AccountModel)
        .filter(AccountModel.id == account_id, AccountModel.user_id == user_id)
        .first()
    )


def owned_category(db: Session, user_id: uuid.UUID, category_id: uuid.UUID):
    """Return the user's spending category with this id, or None.

    Checked on every write, since the id comes from the client.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        category_id: The category to fetch.

    Returns:
        The category, or None when it is missing or another user's.
    """
    return (
        db.query(SpendCategoryModel)
        .filter(SpendCategoryModel.id == category_id, SpendCategoryModel.user_id == user_id)
        .first()
    )


def owned_course(db: Session, user_id: uuid.UUID, course_id: uuid.UUID):
    """Return the user's course with this id, or None.

    Checked on every write, since the id comes from the client.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        course_id: The course to fetch.

    Returns:
        The course, or None when it is missing or another user's.
    """
    return (
        db.query(CourseModel)
        .filter(CourseModel.id == course_id, CourseModel.user_id == user_id)
        .first()
    )


def tuition_payment_ids(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, uuid.UUID]:
    """Return transaction id to tuition payment id for every row a payment owns.

    One query for the whole ledger, so a list can send tuition rows to their own
    editor.

    Args:
        db: Open database session.
        user_id: Owner of the rows.

    Returns:
        Payment id by the id of the ledger row it owns.
    """
    rows = (
        db.query(TuitionPaymentModel.transaction_id, TuitionPaymentModel.id)
        .filter(TuitionPaymentModel.user_id == user_id)
        .all()
    )
    return {transaction_id: payment_id for transaction_id, payment_id in rows}


def group_sizes(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """Return how many rows share each group id, in one grouped query.

    Args:
        db: Open database session.
        user_id: Owner of the rows.

    Returns:
        Row count by group id; ungrouped rows are absent.
    """
    rows = (
        db.query(TransactionModel.group_id, func.count(TransactionModel.id))
        .filter(TransactionModel.user_id == user_id, TransactionModel.group_id.isnot(None))
        .group_by(TransactionModel.group_id)
        .all()
    )
    return {group_id: count for group_id, count in rows}


def paycheque_groups(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, uuid.UUID]:
    """Return group id to paycheque id for every deposit a cheque owns.

    Args:
        db: Open database session.
        user_id: Owner of the rows.

    Returns:
        Cheque id by the group id of the rows its net became.
    """
    rows = (
        db.query(PaychequeModel.group_id, PaychequeModel.id)
        .filter(PaychequeModel.user_id == user_id, PaychequeModel.group_id.isnot(None))
        .all()
    )
    return {group_id: cheque_id for group_id, cheque_id in rows}


def mark_handled(db: Session, user_id: uuid.UUID, rows) -> None:
    """Record on each row's standing instruction that the row's date is dealt with.

    A generated payment counts as written only while a row sits on its date, so
    deleting one, or moving it to another day, used to have the next catch-up
    write it again (audit C1). Adding the date to the rule's skipped dates, in the
    caller's commit, makes the student's change stick. Changes rows only.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        rows: Ledger rows about to be deleted or re-dated; rows no rule wrote are
            ignored.
    """
    dates: dict[uuid.UUID, set[date]] = {}
    for row in rows:
        if row.recurring_id is not None:
            dates.setdefault(row.recurring_id, set()).add(row.occurred_on)
    if not dates:
        return

    rules = db.query(RecurringTransactionModel).filter(
        RecurringTransactionModel.id.in_(list(dates)),
        RecurringTransactionModel.user_id == user_id,
    )
    for rule in rules:
        skipped = {date.fromisoformat(str(value)) for value in (rule.skipped_dates or [])}
        # Rewritten whole: SQLAlchemy does not track mutation inside a JSON column.
        rule.skipped_dates = sorted(day.isoformat() for day in skipped | dates[rule.id])


def signed(kind: TransactionKind, amount: float) -> float:
    """Return an amount signed by kind: positive for income, negative otherwise.

    Args:
        kind: The transaction kind.
        amount: The magnitude, positive.

    Returns:
        The signed amount; a transfer's caller signs each leg itself.
    """
    return amount if kind == TransactionKind.INCOME else -amount


def as_schema(
    transaction: TransactionModel,
    group_size: int = 1,
    tuition_payment_id: uuid.UUID | None = None,
    paycheque_id: uuid.UUID | None = None,
) -> Transaction:
    """Build a detached response from a row, without touching the row itself.

    Args:
        transaction: The row.
        group_size: How many rows share its group.
        tuition_payment_id: The tuition payment that owns it, if any.
        paycheque_id: The paycheque that owns its group, if any.

    Returns:
        The response, with `amount` as a magnitude and `signed_amount` as stored.
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
        business_percent=transaction.business_percent,
        tuition_payment_id=tuition_payment_id,
        paycheque_id=paycheque_id,
        recurring_id=transaction.recurring_id,
    )


def list_transactions(
    db: Session,
    user_id: uuid.UUID,
    account_id: uuid.UUID | None = None,
    limit: int = 100,
    start: date | None = None,
    end: date | None = None,
):
    """Return the user's ledger rows newest first, optionally for one account or window.

    `limit` drops the oldest rows, so a caller after a stretch of time should narrow
    with `start` and `end` rather than page.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        account_id: Only this account's rows; None for every account.
        limit: Most rows to return.
        start: Earliest date, inclusive; None for no bound.
        end: Latest date, inclusive; None for no bound.

    Returns:
        The rows with group sizes, owning tuition payments and owning paycheques
        attached.

    Raises:
        ValueError: If `start` is after `end`.
        LookupError: If `account_id` is not one of the user's accounts.
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
    cheques = paycheque_groups(db, user_id)
    return [
        as_schema(row, sizes.get(row.group_id, 1), tuition.get(row.id), cheques.get(row.group_id))
        for row in rows
    ]


def create_transaction(
    db: Session, user_id: uuid.UUID, data: TransactionCreate, *, recurring_id: uuid.UUID | None = None
):
    """Record income or an expense on one of the user's accounts.

    A category and a course are kept only on an expense. Commits.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        data: The transaction; its amount is a positive magnitude.
        recurring_id: The standing instruction writing it, so the row and the
            mark that its date is paid land in one commit; None for a row entered
            by hand.

    Returns:
        The new row's response; None when the account is not the user's.

    Raises:
        ValueError: If the kind is transfer, or the category or course is not the
            user's.
    """
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
        recurring_id=recurring_id,
    )
    try:
        db.add(transaction)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(transaction)
    return as_schema(transaction)


def create_transfer(
    db: Session, user_id: uuid.UUID, data: TransferCreate, *, recurring_id: uuid.UUID | None = None
):
    """Move money between two of the user's accounts as two rows in one commit.

    Both rows carry the category, so either one shows it; only the outgoing row
    counts in a category's spending.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        data: The amount, date, description, both accounts and the category.
        recurring_id: The standing instruction writing it, set on both rows; None
            for a transfer entered by hand.

    Returns:
        The outgoing and incoming rows' responses; None when either account is
        not the user's.

    Raises:
        ValueError: If the category is not the user's.
    """
    source = owned_account(db, user_id, data.from_account_id)
    target = owned_account(db, user_id, data.to_account_id)
    if source is None or target is None:
        return None

    if data.category_id is not None and owned_category(db, user_id, data.category_id) is None:
        raise ValueError("That category does not exist")

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
            category_id=data.category_id,
            recurring_id=recurring_id,
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
    """Return one of the user's rows with its group size, or None if not theirs.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        transaction_id: The row to fetch.

    Returns:
        The row as a `Transaction` with `group_size` set, or None.
    """
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
    """Change the fields sent on one of the user's rows.

    A new amount keeps the row's direction. On a transfer the other leg follows the
    amount, date, description and category; a deposit's other rows are left alone.
    Moving a standing instruction's payment to another day marks the day it was
    due as paid and makes the row the student's own, so the catch-up neither
    writes that day again nor counts the new one as a payment of the rule
    (audit C1). Commits.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        transaction_id: The row.
        data: The fields to change.

    Returns:
        The updated row's response; None when it is not the user's.

    Raises:
        ValueError: If the amount of a tuition payment's row is changed (that goes
            through the tuition editor), the category or course is not the user's,
            or the change would give one standing payment two rows on one account
            and day.
    """
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

    # Only money going out can be a business expense (Phase 4 item 15).
    if update_data.get("business_percent") is not None and transaction.kind != TransactionKind.EXPENSE.value:
        raise ValueError("Only an expense can be a business expense")

    new_amount = update_data.pop("amount", None)

    redated = (
        transaction.recurring_id is not None
        and "occurred_on" in update_data
        and update_data["occurred_on"] != transaction.occurred_on
    )
    if redated:
        mark_handled(db, user_id, [transaction])
        transaction.recurring_id = None

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
                if redated:
                    partner.recurring_id = None
            if "description" in update_data:
                partner.description = transaction.description
            if "category_id" in update_data:
                partner.category_id = transaction.category_id

    try:
        db.commit()
    except IntegrityError as exc:
        # Moving a deposit row onto an account another row of the same payment
        # already holds: the one-payment-per-account rule (audit M3).
        db.rollback()
        raise ValueError("Another row of this standing payment is already on that account and day") from exc
    db.refresh(transaction)
    return as_schema(transaction)


def delete_transaction(
    db: Session,
    user_id: uuid.UUID,
    transaction_id: uuid.UUID,
    scope: str = "group",
):
    """Delete one row, or the whole group it belongs to, with whatever owns it.

    A transfer is always deleted whole. For a deposit, `scope` "row" drops one
    allocation and "group" the whole deposit. A tuition payment owning the row, and
    a paycheque or sinking contribution owning its group, are deleted too. A
    standing instruction's payment marks its date as dealt with, so the catch-up
    doesn't write it again (audit C1). Commits.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        transaction_id: The row.
        scope: "group" (the default) or "row".

    Returns:
        A copy of the row the caller named; None when it is not the user's.

    Raises:
        ValueError: If `scope` is "row" on a paycheque's row: one share of a
            cheque can't go without the cheque, and the cheque can't go leaving
            the other shares unexplained (audit H5).

    Note:
        A shift record pointing at a cash-tip row makes the delete fail its
        foreign key.
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

    doomed_cheques = []
    if transaction.group_id is not None:
        doomed_cheques = (
            db.query(PaychequeModel)
            .filter(
                PaychequeModel.user_id == user_id,
                PaychequeModel.group_id == transaction.group_id,
            )
            .all()
        )
    # Refused before anything is touched. This used to delete the cheque, its
    # deductions and its verdict from Jobs, and leave the other shares in the
    # ledger as anonymous income.
    if doomed_cheques and scope == "row" and not is_transfer:
        raise ValueError(
            "This is one share of a paycheque. Edit the cheque on the Jobs page, or delete the whole cheque"
        )

    whole_group = transaction.group_id is not None and (is_transfer or scope == "group")
    going = (
        db.query(TransactionModel)
        .filter(TransactionModel.group_id == transaction.group_id, TransactionModel.user_id == user_id)
        .all()
        if whole_group else [transaction]
    )
    mark_handled(db, user_id, going)

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
    # rows, not one; found above.
    if transaction.group_id is not None:
        # Deductions follow through the relationship's delete-orphan cascade.
        for cheque in doomed_cheques:
            db.delete(cheque)

        # A sinking-fund contribution owns the transfer it wrote, so removing
        # the transfer must remove the contribution -- otherwise the fund goes
        # on claiming money that is no longer set aside anywhere.
        db.query(SinkingContributionModel).filter(
            SinkingContributionModel.group_id == transaction.group_id
        ).delete(synchronize_session=False)

    if whole_group:
        db.query(TransactionModel).filter(
            TransactionModel.group_id == transaction.group_id,
            TransactionModel.user_id == user_id,
        ).delete(synchronize_session=False)
    else:
        db.delete(transaction)

    db.commit()
    return removed
