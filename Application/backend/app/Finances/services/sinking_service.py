"""Putting money aside for something that lands all at once.

Tuition in January is not a surprise, but it behaves like one if nothing
reserves for it. A fund says what the thing costs and when it is due; the
monthly figure falls out of those two and what has already been set aside.

**Nothing about the schedule is stored.** `per_month` is
`(target − saved) ÷ months left`, recomputed on every read. A stored schedule
goes stale the moment a month is missed or the target changes, and the recovery
from either is the same division — so storing it would only be a second answer
that could disagree with the first.

**A contribution row exists only once the money has moved.** A planned
contribution is not a transaction for the same reason a projected payment is
not: nothing has moved, and a balance counting it would report money as gone
while it is still in the account.

**How this reaches safe-to-spend.** A *confirmed* contribution needs no special
handling — the money is in a savings account, which safe-to-spend already
excludes. What it subtracts is this month's contribution while it is still a
promise. Doing both would take the same money off twice.
"""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app._database.models import (
    AccountModel,
    SinkingContributionModel,
    SinkingFundModel,
    TransactionModel,
    utc_now,
)
from app.Finances.schemas.sinking import (
    ContributionRequest,
    SinkingContribution,
    SinkingFund,
    SinkingFundCreate,
    SinkingFundUpdate,
)
from app.Finances.schemas.transaction import TransactionKind
from app.Tasks.services.task_service import user_exists
from app.shared.dates import today
from app.shared.money import money


# Every function that produces a figure takes an `on_day`. The monthly amount
# depends on how many months are left, so a service that reads the wall clock
# cannot be tested at a fixed date -- and a test that computes its expectation
# from the same clock agrees with any answer, including a wrong one.


def first_of(day: date) -> date:
    return day.replace(day=1)


def months_between(start: date, end: date) -> int:
    """Whole months from one date to another, by calendar month rather than days."""
    return (end.year - start.year) * 12 + (end.month - start.month)


def months_left(due_on: date, anchor: date) -> int:
    """Contributions remaining, counting this month.

    Zero once the due date is behind us, which is what makes `per_month` fall
    back to the whole remainder rather than dividing by nothing.
    """
    if due_on < anchor:
        return 0
    return max(0, months_between(anchor, due_on)) + 1


def owned_account(db: Session, user_id: uuid.UUID, account_id: uuid.UUID):
    return (
        db.query(AccountModel)
        .filter(AccountModel.id == account_id, AccountModel.user_id == user_id)
        .first()
    )


def as_schema(fund: SinkingFundModel, anchor: date) -> SinkingFund:
    contributions = sorted(fund.contributions or [], key=lambda row: row.for_month)
    saved = money(sum(row.amount for row in contributions))
    remaining = money(max(0.0, fund.target_amount - saved))
    left = months_left(fund.due_on, anchor)

    # With the due date gone and money still owed, the whole remainder is due
    # now. Spreading it over zero months is a division by nothing; spreading it
    # over one more would quietly move the deadline.
    per_month = money(remaining / left) if left > 0 else remaining

    this_month = first_of(anchor)
    funded = any(row.for_month == this_month for row in contributions)

    return SinkingFund(
        id=fund.id,
        name=fund.name,
        target_amount=fund.target_amount,
        due_on=fund.due_on,
        from_account_id=fund.from_account_id,
        to_account_id=fund.to_account_id,
        archived=fund.archived,
        created_at=fund.created_at,
        saved=saved,
        remaining=remaining,
        months_left=left,
        per_month=per_month,
        funded_this_month=funded,
        unfunded_this_month=0.0 if funded or remaining == 0 else per_month,
        overdue=fund.due_on < anchor and remaining > 0,
        contributions=[SinkingContribution.model_validate(row) for row in contributions],
    )


def list_funds(
    db: Session,
    user_id: uuid.UUID,
    include_archived: bool = False,
    on_day: date | None = None,
):
    if not user_exists(db, user_id):
        return None

    query = db.query(SinkingFundModel).filter(SinkingFundModel.user_id == user_id)
    if not include_archived:
        query = query.filter(SinkingFundModel.archived.is_(False))

    anchor = on_day or today()
    funds = query.order_by(SinkingFundModel.due_on).all()
    return [as_schema(fund, anchor) for fund in funds]


def get_fund(db: Session, user_id: uuid.UUID, fund_id: uuid.UUID):
    return (
        db.query(SinkingFundModel)
        .filter(SinkingFundModel.id == fund_id, SinkingFundModel.user_id == user_id)
        .first()
    )


def check_accounts(db: Session, user_id: uuid.UUID, from_id, to_id) -> None:
    if from_id == to_id:
        raise ValueError("Money has to move between two different accounts")
    if owned_account(db, user_id, from_id) is None:
        raise ValueError("That source account does not exist")
    if owned_account(db, user_id, to_id) is None:
        raise ValueError("That destination account does not exist")


def create_fund(
    db: Session, user_id: uuid.UUID, data: SinkingFundCreate, on_day: date | None = None
):
    if not user_exists(db, user_id):
        return None

    check_accounts(db, user_id, data.from_account_id, data.to_account_id)

    fund = SinkingFundModel(
        id=uuid.uuid4(),
        user_id=user_id,
        name=data.name.strip(),
        target_amount=money(data.target_amount),
        due_on=data.due_on,
        from_account_id=data.from_account_id,
        to_account_id=data.to_account_id,
        archived=data.archived,
        created_at=utc_now(),
    )
    db.add(fund)
    db.commit()
    db.refresh(fund)
    return as_schema(fund, on_day or today())


def update_fund(
    db: Session,
    user_id: uuid.UUID,
    fund_id: uuid.UUID,
    data: SinkingFundUpdate,
    on_day: date | None = None,
):
    fund = get_fund(db, user_id, fund_id)
    if fund is None:
        return None

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(fund, key, value)

    check_accounts(db, user_id, fund.from_account_id, fund.to_account_id)

    db.commit()
    db.refresh(fund)
    # Nothing recalculates here: raising the target or moving the date changes
    # per_month on the next read, which is the whole point of not storing it.
    return as_schema(fund, on_day or today())


def transfer_rows(
    db: Session,
    user_id: uuid.UUID,
    fund: SinkingFundModel,
    amount: float,
    occurred_on: date,
    group_id: uuid.UUID,
) -> list[TransactionModel]:
    """The two halves of the transfer a contribution writes, unsaved.

    Built here rather than through `record_transfer`, which commits on its own:
    the transfer and the contribution row have to land together, or a failure
    halfway leaves money moved with nothing explaining why.
    """
    source = owned_account(db, user_id, fund.from_account_id)
    target = owned_account(db, user_id, fund.to_account_id)
    if source is None or target is None:
        raise ValueError("That account does not exist")

    return [
        TransactionModel(
            id=uuid.uuid4(),
            user_id=user_id,
            account_id=account.id,
            kind=TransactionKind.TRANSFER.value,
            amount=signed,
            description=f"{fund.name} fund",
            occurred_on=occurred_on,
            group_id=group_id,
        )
        for account, signed in ((source, -amount), (target, amount))
    ]


def contribute(
    db: Session, user_id: uuid.UUID, fund_id: uuid.UUID, data: ContributionRequest
):
    """Set this month's money aside for real, writing the transfer."""
    fund = get_fund(db, user_id, fund_id)
    if fund is None:
        return None

    anchor = data.occurred_on or today()
    for_month = first_of(anchor)

    already = (
        db.query(SinkingContributionModel)
        .filter(
            SinkingContributionModel.fund_id == fund.id,
            SinkingContributionModel.for_month == for_month,
        )
        .first()
    )
    if already is not None:
        raise ValueError("This month has already been set aside")

    current = as_schema(fund, anchor)
    if current.remaining == 0:
        raise ValueError("This fund has already reached its target")

    amount = money(data.amount if data.amount is not None else current.per_month)
    if amount <= 0:
        raise ValueError("There is nothing left to set aside")
    # Overshooting the target would put money into the fund that the fund does
    # not need, and the ledger would then disagree with what the fund says it
    # holds.
    amount = min(amount, current.remaining)

    group_id = uuid.uuid4()
    db.add_all(transfer_rows(db, user_id, fund, amount, anchor, group_id))
    db.add(SinkingContributionModel(
        id=uuid.uuid4(),
        fund_id=fund.id,
        for_month=for_month,
        amount=amount,
        group_id=group_id,
        confirmed_at=utc_now(),
    ))

    db.commit()
    db.refresh(fund)
    return as_schema(fund, anchor)


def clear_transfer(db: Session, user_id: uuid.UUID, group_id: uuid.UUID | None) -> None:
    """Remove the ledger rows a contribution wrote. Literal filter, one model."""
    if group_id is None:
        return

    db.query(TransactionModel).filter(
        TransactionModel.user_id == user_id,
        TransactionModel.group_id == group_id,
    ).delete(synchronize_session=False)


def undo_contribution(
    db: Session,
    user_id: uuid.UUID,
    fund_id: uuid.UUID,
    contribution_id: uuid.UUID,
    on_day: date | None = None,
):
    """Take back a month's set-aside, moving the money with it."""
    fund = get_fund(db, user_id, fund_id)
    if fund is None:
        return None

    row = (
        db.query(SinkingContributionModel)
        .filter(
            SinkingContributionModel.id == contribution_id,
            SinkingContributionModel.fund_id == fund.id,
        )
        .first()
    )
    if row is None:
        return None

    clear_transfer(db, user_id, row.group_id)
    db.delete(row)
    db.commit()
    db.refresh(fund)
    return as_schema(fund, on_day or today())


def delete_fund(
    db: Session, user_id: uuid.UUID, fund_id: uuid.UUID, on_day: date | None = None
):
    """Remove a fund, its contributions, and the transfers they wrote.

    All of it, because a contribution only ever existed to serve the fund: left
    behind, the transfers would sit in the ledger under a name nothing explains.
    Archiving is the way to keep the history.
    """
    fund = get_fund(db, user_id, fund_id)
    if fund is None:
        return None

    removed = as_schema(fund, on_day or today())
    for contribution in list(fund.contributions or []):
        clear_transfer(db, user_id, contribution.group_id)

    db.delete(fund)
    db.commit()
    return removed


def unfunded_total(db: Session, user_id: uuid.UUID, anchor: date) -> float:
    """This month's promised-but-unmoved contributions, for safe-to-spend."""
    funds = (
        db.query(SinkingFundModel)
        .filter(
            SinkingFundModel.user_id == user_id,
            SinkingFundModel.archived.is_(False),
        )
        .all()
    )
    return money(sum(as_schema(fund, anchor).unfunded_this_month for fund in funds))
