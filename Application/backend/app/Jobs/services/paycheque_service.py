"""Service functions for paycheques: what arrived, what was deducted, and expected.

The tuition payment in reverse: gross pay and named deductions live on the
cheque, and only the net reaches the ledger, split across accounts by income
share as several rows tied by the cheque's `group_id`. The expectation a cheque
is compared with depends on the job's kind and is frozen when it is recorded.
"""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app._database.models import (
    JobModel,
    PaychequeDeductionModel,
    PaychequeModel,
    ShiftRecordModel,
    TransactionModel,
)
from app.Finances.schemas.transaction import TransactionKind
from app.Finances.services.deposit_service import active_accounts, split_income
from app.Jobs.schemas.job import JobKind
from app.Jobs.schemas.paycheque import (
    Deduction,
    Paycheque,
    PaychequeCreate,
    PaychequePreview,
    PaychequeUpdate,
)
from app.Jobs.services.job_service import list_shifts, owned_job
from app.Jobs.services.pay_rules import Worked, split
from app.Tasks.services.task_service import user_exists
from app.shared.money import money


def net_of(gross: float, deductions) -> float:
    """Return gross pay less the deductions' amounts, rounded to cents.

    Args:
        gross: Gross pay in dollars.
        deductions: Entries with an `amount` in dollars.

    Returns:
        The net pay in dollars.
    """
    return money(gross - sum(entry.amount for entry in deductions))


def as_schema(db: Session, row: PaychequeModel) -> Paycheque:
    """Build a cheque's response, with its job's name, net and variance.

    Args:
        db: Open database session.
        row: The cheque row.

    Returns:
        The cheque; `variance` is None without a stored expectation.
    """
    job = db.query(JobModel).filter(JobModel.id == row.job_id).first()
    deductions = [Deduction.model_validate(d) for d in row.deductions]
    net = net_of(row.gross_amount, deductions)

    return Paycheque(
        id=row.id,
        job_id=row.job_id,
        job_name=job.name if job else "",
        occurred_on=row.occurred_on,
        gross_amount=row.gross_amount,
        deductions=deductions,
        net_amount=net,
        period_start=row.period_start,
        period_end=row.period_end,
        expected_gross=row.expected_gross,
        variance=(
            money(row.gross_amount - row.expected_gross)
            if row.expected_gross is not None
            else None
        ),
        notes=row.notes,
    )


def expected_for(
    db: Session,
    user_id: uuid.UUID,
    job: JobModel,
    period_start: date | None,
    period_end: date | None,
) -> PaychequePreview | None:
    """Return what a job's shifts in a pay period say its cheque should come to.

    Hourly jobs get their counted hours with BC overtime at each shift's rate;
    salaried jobs their period amount; both add tips paid through payroll. Contract
    jobs get the hours and no figure. Vacation pay is left out.

    Args:
        db: Open database session.
        user_id: Whose shifts.
        job: The job.
        period_start: First day of the period; None means no period.
        period_end: Last day of the period; None means no period.

    Returns:
        The preview; None when either end of the period is missing.
    """
    if period_start is None or period_end is None:
        return None

    shifts = list_shifts(db, user_id, period_start, period_end) or []
    mine = [shift for shift in shifts if shift.job_id == job.id]

    minutes = sum(shift.counted_minutes for shift in mine)
    assumed = sum(1 for shift in mine if shift.assumed)
    # Only tips paid through payroll. A cash tip is money already in hand and
    # will never appear on a cheque, so counting it here would make every cheque
    # look short by the amount of cash earned.
    on_cheque_tips = money(
        sum(shift.tip_amount for shift in mine if not shift.tip_is_cash)
    )

    expected: float | None
    if job.kind == JobKind.HOURLY.value:
        # BC overtime applied (pay_rules, ESA s.40): a 9-hour Tuesday paid as
        # nine straight hours is exactly the shortfall this exists to catch.
        # Vacation pay is not: whether it is on each cheque or held is the
        # employer's choice, and the on-demand check covers both.
        worked = [
            Worked(shift.on_date, shift.counted_minutes,
                   shift.rate_override or job.hourly_rate or 0.0, shift.scheduled_start)
            for shift in mine if shift.counted_minutes > 0
        ]
        earned = sum(money(portion.amount) for portion in split(worked))
        expected = money(earned + on_cheque_tips)
    elif job.kind == JobKind.SALARIED.value:
        # The period amount is the prediction. Hours are what the job costs you,
        # never evidence that it underpaid.
        expected = money((job.period_amount or 0.0) + on_cheque_tips)
    else:
        expected = None

    return PaychequePreview(
        job_id=job.id,
        period_start=period_start,
        period_end=period_end,
        expected_gross=expected,
        shift_count=len(mine),
        counted_minutes=minutes,
        assumed_count=assumed,
        on_cheque_tips=on_cheque_tips,
    )


def preview_paycheque(
    db: Session,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    period_start: date,
    period_end: date,
):
    """Return what a cheque for one of the user's jobs and a period should come to.

    Args:
        db: Open database session.
        user_id: Whose job.
        job_id: The job.
        period_start: First day of the period.
        period_end: Last day of the period.

    Returns:
        The preview; None when the job is not the user's.
    """
    job = owned_job(db, user_id, job_id)
    if job is None:
        return None

    return expected_for(db, user_id, job, period_start, period_end)


def deposit_rows(
    db: Session,
    user_id: uuid.UUID,
    net: float,
    allocations,
    occurred_on: date,
    description: str,
    group_id: uuid.UUID,
) -> list[TransactionModel]:
    """Build, unsaved, the income rows a cheque's net becomes.

    Built here rather than through `record_deposit`, which commits on its own, so
    the rows and the cheque land in one transaction.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        net: The cheque's net, in dollars.
        allocations: Explicit amounts per account; empty or None splits by income
            share among unarchived accounts.
        occurred_on: The rows' date.
        description: The rows' description.
        group_id: The id tying the rows to the cheque.

    Returns:
        The rows, skipping zero allocations.

    Raises:
        ValueError: If nothing can be split (no shares and no allocations) or an
            allocation names an account that is not one of the user's unarchived
            accounts.
    """
    accounts = active_accounts(db, user_id)
    by_id = {account.id: account for account in accounts}

    split = allocations or split_income(net, accounts)
    if not split:
        raise ValueError(
            "No account has an income share yet. Set shares in your accounts, "
            "or choose where this cheque should land."
        )

    unknown = [entry.account_id for entry in split if entry.account_id not in by_id]
    if unknown:
        raise ValueError("That account does not exist")

    return [
        TransactionModel(
            id=uuid.uuid4(),
            user_id=user_id,
            account_id=entry.account_id,
            kind=TransactionKind.INCOME.value,
            amount=entry.amount,
            description=description,
            occurred_on=occurred_on,
            group_id=group_id,
        )
        for entry in split
        if entry.amount > 0
    ]


def list_paycheques(db: Session, user_id: uuid.UUID, job_id: uuid.UUID | None = None):
    """Return the user's paycheques, latest first.

    Args:
        db: Open database session.
        user_id: Whose cheques.
        job_id: Only this job's cheques; None for all.

    Returns:
        The cheques; None when the user does not exist.
    """
    if not user_exists(db, user_id):
        return None

    query = db.query(PaychequeModel).filter(PaychequeModel.user_id == user_id)
    if job_id is not None:
        query = query.filter(PaychequeModel.job_id == job_id)

    rows = query.order_by(PaychequeModel.occurred_on.desc()).all()
    return [as_schema(db, row) for row in rows]


def get_paycheque(db: Session, user_id: uuid.UUID, paycheque_id: uuid.UUID):
    """Return one of the user's cheques, or None when it is not theirs.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        paycheque_id: The cheque to fetch.

    Returns:
        The cheque as its API schema, or None when it is missing or another user's.
    """
    row = (
        db.query(PaychequeModel)
        .filter(PaychequeModel.id == paycheque_id, PaychequeModel.user_id == user_id)
        .first()
    )
    return None if row is None else as_schema(db, row)


def record_paycheque(db: Session, user_id: uuid.UUID, data: PaychequeCreate):
    """Record a cheque: the cheque, its deductions and the ledger rows for its net.

    The expectation for its period is computed now and stored. One commit.

    Args:
        db: Open database session.
        user_id: Whose cheque.
        data: The cheque, its deductions and any allocations.

    Returns:
        The recorded cheque; None when the job is not the user's.

    Raises:
        ValueError: If the net cannot be split or an allocation names an account
            that is not the user's.
    """
    job = owned_job(db, user_id, data.job_id)
    if job is None:
        return None

    net = net_of(data.gross_amount, data.deductions)
    group_id = uuid.uuid4()

    preview = expected_for(db, user_id, job, data.period_start, data.period_end)

    cheque = PaychequeModel(
        id=uuid.uuid4(),
        user_id=user_id,
        job_id=job.id,
        group_id=group_id,
        occurred_on=data.occurred_on,
        gross_amount=money(data.gross_amount),
        period_start=data.period_start,
        period_end=data.period_end,
        expected_gross=preview.expected_gross if preview else None,
        notes=data.notes,
    )
    db.add(cheque)
    db.flush()

    for entry in data.deductions:
        db.add(PaychequeDeductionModel(
            id=uuid.uuid4(),
            paycheque_id=cheque.id,
            description=entry.description,
            amount=money(entry.amount),
        ))

    rows = deposit_rows(
        db, user_id, net, data.allocations, data.occurred_on,
        f"{job.name} pay", group_id,
    )
    db.add_all(rows)

    db.commit()
    db.refresh(cheque)
    return as_schema(db, cheque)


def clear_deposit(db: Session, user_id: uuid.UUID, group_id: uuid.UUID | None) -> None:
    """Delete the ledger rows a cheque wrote; nothing for a None group.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        group_id: The cheque's deposit group; None does nothing.
    """
    if group_id is None:
        return

    db.query(TransactionModel).filter(
        TransactionModel.user_id == user_id,
        TransactionModel.group_id == group_id,
    ).delete(synchronize_session=False)


def update_paycheque(
    db: Session, user_id: uuid.UUID, paycheque_id: uuid.UUID, data: PaychequeUpdate
):
    """Correct one of the user's cheques, rewriting its ledger rows.

    Whatever field changes, the old rows are deleted and the net is split again,
    by the patch's allocations or else by today's income shares. Deductions sent
    replace the old ones. `expected_gross` is never recomputed. One commit.

    Args:
        db: Open database session.
        user_id: Whose cheque.
        paycheque_id: The cheque.
        data: The fields to change.

    Returns:
        The corrected cheque; None when it is not the user's.

    Raises:
        ValueError: If the period ends before it starts, the deductions reach the
            gross, or the net cannot be split.
    """
    cheque = (
        db.query(PaychequeModel)
        .filter(PaychequeModel.id == paycheque_id, PaychequeModel.user_id == user_id)
        .first()
    )
    if cheque is None:
        return None

    job = db.query(JobModel).filter(JobModel.id == cheque.job_id).first()
    update_data = data.model_dump(exclude_unset=True)
    deductions = update_data.pop("deductions", None)
    allocations = update_data.pop("allocations", None)

    for key, value in update_data.items():
        setattr(cheque, key, value)

    if deductions is not None:
        db.query(PaychequeDeductionModel).filter(
            PaychequeDeductionModel.paycheque_id == cheque.id
        ).delete(synchronize_session=False)
        for entry in data.deductions or []:
            db.add(PaychequeDeductionModel(
                id=uuid.uuid4(),
                paycheque_id=cheque.id,
                description=entry.description,
                amount=money(entry.amount),
            ))
        db.flush()

    if cheque.period_start and cheque.period_end and cheque.period_end < cheque.period_start:
        raise ValueError("A pay period cannot end before it starts")

    # Deliberately not db.refresh: that reloads the row from the database and
    # throws away the edits above, so correcting the gross silently kept the old
    # one. Flush writes them instead, and the deductions are read back by query
    # rather than through a relationship that has not been reloaded.
    db.flush()
    current = (
        db.query(PaychequeDeductionModel)
        .filter(PaychequeDeductionModel.paycheque_id == cheque.id)
        .all()
    )
    net = net_of(cheque.gross_amount, current)
    if net <= 0:
        raise ValueError("Deductions cannot come to more than the gross")

    clear_deposit(db, user_id, cheque.group_id)
    cheque.group_id = uuid.uuid4()
    db.add_all(deposit_rows(
        db, user_id, net, data.allocations if allocations is not None else None,
        cheque.occurred_on, f"{job.name if job else 'Job'} pay", cheque.group_id,
    ))

    db.commit()
    db.refresh(cheque)
    return as_schema(db, cheque)


def delete_paycheque(db: Session, user_id: uuid.UUID, paycheque_id: uuid.UUID):
    """Delete a cheque and the ledger rows it wrote.

    Its deductions go through the relationship's cascade. Commits.

    Args:
        db: Open database session.
        user_id: Whose cheque.
        paycheque_id: The cheque.

    Returns:
        A copy of the deleted cheque; None when it is not the user's.
    """
    cheque = (
        db.query(PaychequeModel)
        .filter(PaychequeModel.id == paycheque_id, PaychequeModel.user_id == user_id)
        .first()
    )
    if cheque is None:
        return None

    removed = as_schema(db, cheque)

    clear_deposit(db, user_id, cheque.group_id)
    # The deductions go with it through the relationship's delete-orphan
    # cascade. Deleting them here as well left SQLAlchemy expecting to remove
    # rows that were already gone, and warning about it on every commit.
    db.delete(cheque)
    db.commit()
    return removed
