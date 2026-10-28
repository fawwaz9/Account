"""Service functions for standing instructions and the payments they write.

The rule is stored; a payment becomes a real ledger row only once its date has
come, because a balance is the sum of its rows. Later dates stay projections
(`upcoming`). Payments are written through the ordinary money services, so a
recurring transfer or deposit is identical to one entered by hand; there is no
scheduler, and the Budget page runs the catch-up on every load.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app._database.models import (
    AccountModel,
    RecurringTransactionModel,
    TransactionModel,
    UserModel,
)
from app.Calendar.schemas.event import Recurrence
from app.Calendar.services.event_service import parse_date
from app.Calendar.utils.recurrence import occurrences
from app.Calendar.utils.rule_columns import apply_recurrence, recurrence_of, rule_of
from app.Finances.schemas.deposit import DepositCreate
from app.Finances.schemas.recurring import (
    DEPOSIT,
    EXPENSE,
    TRANSFER,
    RecurringCreate,
    RecurringRun,
    RecurringTransaction,
    RecurringUpdate,
    UpcomingCharge,
)
from app.Finances.schemas.transaction import (
    TransactionCreate,
    TransactionKind,
    TransferCreate,
)
from app.Finances.services.deposit_service import record_deposit
from app.Finances.services.transaction_service import (
    create_transaction,
    create_transfer,
    owned_account,
    owned_category,
)
from app.shared.dates import user_today

#: How far past a missed payment the catch-up still reaches. A rule left alone
#: over a summer should not write four months of rent the moment the app opens
#: again -- past this the student is told, rather than charged.
MAX_CATCHUP_DAYS = 120

#: Longest window the upcoming view will project.
MAX_PROJECTION_DAYS = 400


def attach_rule(db: Session, instruction: RecurringTransactionModel) -> RecurringTransactionModel:
    """Set the derived fields the response expects on an instruction row.

    Attaches `recurrence`, `last_run_on` and `next_due_on` to the instance only;
    `skipped_dates` stays as stored ISO strings.

    Args:
        db: Open database session.
        instruction: The instruction row.

    Returns:
        The same row.
    """
    instruction.recurrence = recurrence_of(instruction)
    # Left as the ISO strings the column stores. Assigning parsed dates back onto
    # a JSON column marks the row dirty with values json.dumps cannot serialize,
    # and the next commit on the session fails; the schema declares list[date],
    # so Pydantic does the conversion on the way out.
    written = written_dates(db, instruction.id)
    instruction.last_run_on = max(written) if written else None
    instruction.next_due_on = next_due(
        instruction, written, user_today(db, instruction.user_id)
    )
    return instruction


def written_dates(db: Session, recurring_id: uuid.UUID) -> set[date]:
    """Return the dates this instruction has already written a payment for.

    (recurring_id, occurred_on) is the dedup key the catch-up relies on.

    Args:
        db: Open database session.
        recurring_id: The instruction.

    Returns:
        The set of dates; empty when nothing is written.
    """
    rows = (
        db.query(TransactionModel.occurred_on)
        .filter(TransactionModel.recurring_id == recurring_id)
        .distinct()
        .all()
    )
    return {row.occurred_on for row in rows}


def next_due(
    instruction: RecurringTransactionModel, written: set[date], horizon: date
) -> date | None:
    """Return the first date on or after `horizon` with no payment written yet.

    Args:
        instruction: The instruction row.
        written: The dates already written.
        horizon: The owner's today.

    Returns:
        The date, looking up to 400 days ahead; None when the rule has run out.
    """
    upcoming = occurrences(
        rule_of(instruction),
        instruction.starts_on,
        horizon,
        add_days(horizon, MAX_PROJECTION_DAYS),
        skipped_of(instruction),
    )
    for day in upcoming:
        if day not in written:
            return day
    return None


def add_days(value: date, count: int) -> date:
    """Return a date moved by a number of days.

    Args:
        value: Starting date.
        count: Days to add; negative moves back.

    Returns:
        The shifted date.
    """
    return value + timedelta(days=count)


def skipped_of(instruction: RecurringTransactionModel) -> list[date]:
    """Return an instruction's cancelled dates, parsed from their stored ISO strings.

    Args:
        instruction: The standing instruction.

    Returns:
        Its skipped dates as `date` objects; empty when none.
    """
    return [parse_date(value) for value in (instruction.skipped_dates or [])]


def user_exists(db: Session, user_id: uuid.UUID) -> bool:
    """Return whether a user row with this id exists.

    Args:
        db: Open database session.
        user_id: Id to look up.

    Returns:
        True when the user row exists.
    """
    return db.query(UserModel).filter(UserModel.id == user_id).first() is not None


# --------------------------------------------------------------------- CRUD --

def list_rules(db: Session, user_id: uuid.UUID, include_inactive: bool = True):
    """Return the user's standing instructions, by start date.

    Args:
        db: Open database session.
        user_id: Whose instructions.
        include_inactive: Also return paused ones.

    Returns:
        The rows with derived fields attached; None when the user does not exist.
    """
    if not user_exists(db, user_id):
        return None

    query = db.query(RecurringTransactionModel).filter(
        RecurringTransactionModel.user_id == user_id
    )
    if not include_inactive:
        query = query.filter(RecurringTransactionModel.active.is_(True))

    rules = query.order_by(RecurringTransactionModel.starts_on).all()
    return [attach_rule(db, rule) for rule in rules]


def get_rule(db: Session, user_id: uuid.UUID, rule_id: uuid.UUID):
    """Return one of the user's instructions with derived fields, or None.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        rule_id: The instruction to fetch.

    Returns:
        The instruction with its derived fields attached, or None when it is missing or
        another user's.
    """
    rule = (
        db.query(RecurringTransactionModel)
        .filter(
            RecurringTransactionModel.id == rule_id,
            RecurringTransactionModel.user_id == user_id,
        )
        .first()
    )
    return None if rule is None else attach_rule(db, rule)


def validate_targets(db: Session, user_id: uuid.UUID, data) -> None:
    """Refuse an account or category id that is not the caller's.

    Args:
        db: Open database session.
        user_id: The caller.
        data: A create body naming accounts and a category.

    Raises:
        ValueError: If either account or the category is not the user's.
    """
    for account_id in (data.account_id, data.to_account_id):
        if account_id is not None and owned_account(db, user_id, account_id) is None:
            raise ValueError("That account does not exist")

    if data.category_id is not None and owned_category(db, user_id, data.category_id) is None:
        raise ValueError("That category does not exist")


def create_rule(db: Session, user_id: uuid.UUID, data: RecurringCreate):
    """Create a standing instruction for the user; nothing reaches the ledger yet.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose instruction.
        data: The instruction; a category is kept only on an expense.

    Returns:
        The new row with derived fields; None when the user does not exist.

    Raises:
        ValueError: If an account or the category is not the user's.
    """
    if not user_exists(db, user_id):
        return None

    validate_targets(db, user_id, data)

    instruction = RecurringTransactionModel(
        id=uuid.uuid4(),
        user_id=user_id,
        kind=data.kind,
        account_id=data.account_id,
        to_account_id=data.to_account_id,
        amount=data.amount,
        description=data.description,
        category_id=data.category_id if data.kind == EXPENSE else None,
        starts_on=data.starts_on,
        skipped_dates=[],
        active=data.active,
    )
    apply_recurrence(instruction, data.recurrence)

    db.add(instruction)
    db.commit()
    db.refresh(instruction)
    return attach_rule(db, instruction)


def update_rule(db: Session, user_id: uuid.UUID, rule_id: uuid.UUID, data: RecurringUpdate):
    """Change the fields sent on one of the user's instructions.

    Payments already written are left alone. Commits.

    Args:
        db: Open database session.
        user_id: Whose instruction.
        rule_id: The instruction.
        data: The fields to change; a null `recurrence` keeps the rule.

    Returns:
        The updated row with derived fields; None when it is not the user's.

    Raises:
        ValueError: If a category is set on anything but an expense or is not the
            user's, or the repeat would end before it starts.

    Note:
        The next catch-up writes every date the edited rule produces in the last
        120 days that has no payment, so moving a rule's day back-fills it.
    """
    instruction = get_rule(db, user_id, rule_id)
    if instruction is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    recurrence = update_data.pop("recurrence", None)

    if update_data.get("category_id") is not None:
        if owned_category(db, user_id, update_data["category_id"]) is None:
            raise ValueError("That category does not exist")
        if instruction.kind != EXPENSE:
            raise ValueError("Only an expense carries a spending category")

    for key, value in update_data.items():
        setattr(instruction, key, value)

    if recurrence is not None:
        apply_recurrence(instruction, data.recurrence)

    if instruction.recur_until is not None and instruction.recur_until < instruction.starts_on:
        raise ValueError("A repeat cannot end before it starts")

    db.commit()
    db.refresh(instruction)
    return attach_rule(db, instruction)


def delete_rule(db: Session, user_id: uuid.UUID, rule_id: uuid.UUID):
    """Delete a standing instruction, keeping every payment it already made.

    The payments lose their link to the rule. Commits.

    Args:
        db: Open database session.
        user_id: Whose instruction.
        rule_id: The instruction.

    Returns:
        A copy of the deleted instruction; None when it is not the user's.
    """
    instruction = get_rule(db, user_id, rule_id)
    if instruction is None:
        return None

    # Detached before the delete: attach_rule has already marked the instance
    # dirty, and deleting it in the same session would otherwise flush an UPDATE
    # for a row that is gone.
    snapshot = RecurringTransaction.model_validate(instruction)

    db.query(TransactionModel).filter(
        TransactionModel.recurring_id == instruction.id
    ).update({TransactionModel.recurring_id: None}, synchronize_session=False)

    db.delete(instruction)
    db.commit()
    return snapshot


def skip_occurrence(db: Session, user_id: uuid.UUID, rule_id: uuid.UUID, on_date: date):
    """Cancel one payment of an instruction, such as a paused month.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose instruction.
        rule_id: The instruction.
        on_date: The date to skip.

    Returns:
        The instruction with derived fields; None when it is not the user's.
    """
    instruction = get_rule(db, user_id, rule_id)
    if instruction is None:
        return None

    skipped = set(skipped_of(instruction))
    skipped.add(on_date)
    # Rewritten whole: SQLAlchemy does not track mutation inside a JSON column,
    # so appending in place never reaches the database.
    instruction.skipped_dates = sorted(day.isoformat() for day in skipped)

    db.commit()
    db.refresh(instruction)
    return attach_rule(db, instruction)


# ------------------------------------------------------------ materialising --

def due_dates(db: Session, instruction: RecurringTransactionModel, through: date) -> list[date]:
    """Return the dates owed but not yet written, oldest first.

    Looks back at most `MAX_CATCHUP_DAYS` from `through`, never before the rule's
    start.

    Args:
        db: Open database session.
        instruction: The instruction row.
        through: The last date that counts as due.

    Returns:
        The missing dates.
    """
    earliest = add_days(through, -MAX_CATCHUP_DAYS)
    window_start = max(instruction.starts_on, earliest)

    wanted = occurrences(
        rule_of(instruction),
        instruction.starts_on,
        window_start,
        through,
        skipped_of(instruction),
    )
    written = written_dates(db, instruction.id)
    return [day for day in wanted if day not in written]


def write_occurrence(
    db: Session, user_id: uuid.UUID, instruction: RecurringTransactionModel, on_date: date
):
    """Write one payment through the ordinary money path for its kind.

    A deposit splits by today's income shares, a transfer writes both legs, and
    income or an expense one row; the rows are then stamped with the rule's id.
    Commits twice: the money service commits the rows, then the stamp.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        instruction: The instruction.
        on_date: The payment's date.

    Returns:
        The rows written.

    Raises:
        ValueError: If the account it points at is gone, or the deposit has no
            income shares to split by.
    """
    if instruction.kind == DEPOSIT:
        # No allocations means "split by each account's income share", and the
        # split is worked out at the moment of payment rather than frozen into
        # the rule -- so changing your shares in September changes how October's
        # paycheque lands, which is what changing them is for.
        created = record_deposit(db, user_id, DepositCreate(
            amount=instruction.amount,
            occurred_on=on_date,
            description=instruction.description or "Deposit",
        ))
    elif instruction.kind == TRANSFER:
        created = create_transfer(db, user_id, TransferCreate(
            amount=instruction.amount,
            occurred_on=on_date,
            description=instruction.description,
            from_account_id=instruction.account_id,
            to_account_id=instruction.to_account_id,
        ))
    else:
        created = create_transaction(db, user_id, TransactionCreate(
            kind=TransactionKind(instruction.kind),
            account_id=instruction.account_id,
            amount=instruction.amount,
            description=instruction.description,
            occurred_on=on_date,
            category_id=instruction.category_id,
        ))

    if created is None:
        raise ValueError("the account it points at no longer exists")

    rows = created if isinstance(created, list) else [created]
    # Stamped after the fact because the money services own row creation, and
    # widening all three of their signatures to carry a recurrence id would put
    # a scheduling concern into the one-off path.
    db.query(TransactionModel).filter(
        TransactionModel.id.in_([row.id for row in rows])
    ).update({TransactionModel.recurring_id: instruction.id}, synchronize_session=False)
    db.commit()

    return rows


def run_due(db: Session, user_id: uuid.UUID, through: date | None = None) -> RecurringRun | None:
    """Write every payment that is owed and not yet written, for all active rules.

    Idempotent through the (recurring_id, occurred_on) check, which is what makes
    calling it on every load safe. A rule that fails is reported, and its later
    dates are left, while the other rules still run.

    Args:
        db: Open database session.
        user_id: Whose instructions.
        through: The last date that counts as due; defaults to the user's today.

    Returns:
        How many rows were written, the rows, and one line per rule that could
        not run; None when the user does not exist.
    """
    if not user_exists(db, user_id):
        return None

    horizon = through or user_today(db, user_id)
    rules = (
        db.query(RecurringTransactionModel)
        .filter(
            RecurringTransactionModel.user_id == user_id,
            RecurringTransactionModel.active.is_(True),
        )
        .order_by(RecurringTransactionModel.starts_on)
        .all()
    )

    written = []
    skipped: list[str] = []

    for instruction in rules:
        for on_date in due_dates(db, instruction, horizon):
            try:
                written.extend(write_occurrence(db, user_id, instruction, on_date))
            except ValueError as exc:
                label = instruction.description or instruction.kind
                skipped.append(f"{label} on {on_date.isoformat()}: {exc}")
                break  # this rule is broken; its later dates will fail the same way

    return RecurringRun(created=len(written), transactions=written, skipped=skipped)


def upcoming(
    db: Session, user_id: uuid.UUID, start: date, end: date
) -> list[UpcomingCharge] | None:
    """Return the payments active rules say are coming in a window, as projections.

    Dates already written are left out. Nothing here is a ledger row.

    Args:
        db: Open database session.
        user_id: Whose instructions.
        start: First date, inclusive.
        end: Last date, inclusive.

    Returns:
        The projected charges by date; None when the user does not exist.

    Raises:
        ValueError: If the window ends before it starts or spans more than
            `MAX_PROJECTION_DAYS` days.
    """
    if not user_exists(db, user_id):
        return None

    if end < start:
        raise ValueError("The window ends before it starts")
    if (end - start).days > MAX_PROJECTION_DAYS:
        raise ValueError(f"A window cannot be longer than {MAX_PROJECTION_DAYS} days")

    rules = (
        db.query(RecurringTransactionModel)
        .filter(
            RecurringTransactionModel.user_id == user_id,
            RecurringTransactionModel.active.is_(True),
            RecurringTransactionModel.starts_on <= end,
        )
        .all()
    )
    names = account_names(db, user_id)

    projected: list[UpcomingCharge] = []
    for instruction in rules:
        already = written_dates(db, instruction.id)
        for on_date in occurrences(
            rule_of(instruction), instruction.starts_on, start, end, skipped_of(instruction)
        ):
            # A date already charged is history, not a commitment.
            if on_date in already:
                continue

            leaving = instruction.kind in (EXPENSE, TRANSFER)
            projected.append(UpcomingCharge(
                recurring_id=instruction.id,
                on_date=on_date,
                kind=instruction.kind,
                amount=instruction.amount,
                signed_amount=-instruction.amount if leaving else instruction.amount,
                description=instruction.description,
                account_id=instruction.account_id,
                account_name=names.get(instruction.account_id),
                to_account_id=instruction.to_account_id,
                category_id=instruction.category_id,
            ))

    projected.sort(key=lambda charge: charge.on_date)
    return projected


def account_names(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, str]:
    """Return the user's account ids mapped to their names.

    Args:
        db: Open database session.
        user_id: Owner of the rows.

    Returns:
        Account id to name, archived accounts included.
    """
    rows = (
        db.query(AccountModel.id, AccountModel.name)
        .filter(AccountModel.user_id == user_id)
        .all()
    )
    return {row.id: row.name for row in rows}
