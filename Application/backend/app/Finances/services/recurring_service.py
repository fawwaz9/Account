"""Standing instructions, and turning the due ones into real money movements.

The rule is stored; the payments are not, until they happen. Expansion goes
through the same engine that draws class times on the calendar -- the whole
point of writing that once.

Two things make this different from a repeating calendar event, and both come
from the same fact: a balance is the sum of its rows.

* An occurrence on or before today is written as a real transaction, because
  the money has moved and a balance that ignores it is wrong.
* An occurrence after today is never written, because the money has not moved
  and a balance that counts it is also wrong. Those stay projections.

Writing a payment goes through the ordinary money services rather than
inserting rows here, so signing, transfer pairing and deposit allocation each
keep living in exactly one place.
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
from app.shared.dates import today

#: How far past a missed payment the catch-up still reaches. A rule left alone
#: over a summer should not write four months of rent the moment the app opens
#: again -- past this the student is told, rather than charged.
MAX_CATCHUP_DAYS = 120

#: Longest window the upcoming view will project.
MAX_PROJECTION_DAYS = 400


def attach_rule(db: Session, instruction: RecurringTransactionModel) -> RecurringTransactionModel:
    """Expose the rule columns as the nested object the schema declares.

    Set on the instance rather than as a model property, for the same reason the
    grades module does it: models.py is imported by this service, so a property
    reaching back into it would be a circular import.
    """
    instruction.recurrence = recurrence_of(instruction)
    # Left as the ISO strings the column stores. Assigning parsed dates back onto
    # a JSON column marks the row dirty with values json.dumps cannot serialize,
    # and the next commit on the session fails; the schema declares list[date],
    # so Pydantic does the conversion on the way out.
    written = written_dates(db, instruction.id)
    instruction.last_run_on = max(written) if written else None
    instruction.next_due_on = next_due(instruction, written)
    return instruction


def written_dates(db: Session, recurring_id: uuid.UUID) -> set[date]:
    """Dates this instruction has already been charged for.

    The dedup key is (recurring_id, occurred_on): one standing instruction
    cannot produce two payments for the same date, however many times the
    catch-up runs.
    """
    rows = (
        db.query(TransactionModel.occurred_on)
        .filter(TransactionModel.recurring_id == recurring_id)
        .distinct()
        .all()
    )
    return {row.occurred_on for row in rows}


def next_due(instruction: RecurringTransactionModel, written: set[date]) -> date | None:
    """The first date on or after today that has not been charged yet."""
    horizon = today()
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
    return value + timedelta(days=count)


def skipped_of(instruction: RecurringTransactionModel) -> list[date]:
    return [parse_date(value) for value in (instruction.skipped_dates or [])]


def user_exists(db: Session, user_id: uuid.UUID) -> bool:
    return db.query(UserModel).filter(UserModel.id == user_id).first() is not None


# --------------------------------------------------------------------- CRUD --

def list_rules(db: Session, user_id: uuid.UUID, include_inactive: bool = True):
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
    """Every account and category named must belong to the caller.

    The same check every one-off write makes: an id from another account would
    otherwise be stored happily, which is how the cross-tenant category bug
    worked.
    """
    for account_id in (data.account_id, data.to_account_id):
        if account_id is not None and owned_account(db, user_id, account_id) is None:
            raise ValueError("That account does not exist")

    if data.category_id is not None and owned_category(db, user_id, data.category_id) is None:
        raise ValueError("That category does not exist")


def create_rule(db: Session, user_id: uuid.UUID, data: RecurringCreate):
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
    """Stop the instruction, keeping every payment it already made.

    The generated transactions are real money that really moved, so they stay
    and simply lose their link back. Deleting them with the rule would rewrite
    history to say the rent was never paid.
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
    """Skip one payment -- a month the subscription was paused."""
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
    """Occurrences owed but not yet written, oldest first."""
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
    """One payment, through the ordinary money path for its kind.

    Dispatching to the existing services rather than inserting rows here is what
    keeps a recurring transfer identical to a hand-entered one: same signing,
    same paired legs, same deposit allocation, same validation.
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
    """Write every payment that is owed and has not been written yet.

    Idempotent: the dedup on (recurring_id, occurred_on) means calling this on
    every page load is safe, which is what makes "open the app and last month's
    rent is already there" work without a scheduler.

    A rule that cannot run is reported rather than raised, so one standing
    instruction pointing at a deleted account does not stop the other five from
    being charged.
    """
    if not user_exists(db, user_id):
        return None

    horizon = through or today()
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
    """Payments the rules say are coming, as projections rather than rows.

    This is what a "what am I already committed to" figure reads. Nothing here
    has moved any money, so nothing here belongs in a balance.
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
    rows = (
        db.query(AccountModel.id, AccountModel.name)
        .filter(AccountModel.user_id == user_id)
        .all()
    )
    return {row.id: row.name for row in rows}
