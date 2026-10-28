"""Service functions for sinking funds: money set aside monthly for a dated cost.

Nothing about the schedule is stored: the monthly figure is (target - saved) /
months left, recomputed on every read. A contribution row exists only once its
transfer is written, and safe-to-spend earmarks only this month's contribution
while it is still a promise. Every figure takes the day it is computed for.
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
from app.shared.dates import user_today
from app.shared.money import money
from app.Finances.services.counted import uncounted_accounts


# Every function that produces a figure takes an `on_day`. The monthly amount
# depends on how many months are left, so a service that reads the wall clock
# cannot be tested at a fixed date -- and a test that computes its expectation
# from the same clock agrees with any answer, including a wrong one.


def first_of(day: date) -> date:
    """Return the first day of the month a date falls in.

    Args:
        day: Any date.

    Returns:
        The first of that month.
    """
    return day.replace(day=1)


def months_between(start: date, end: date) -> int:
    """Return the whole calendar months from one date's month to another's.

    Args:
        start: Earlier date; only its month counts.
        end: Later date; only its month counts.

    Returns:
        Month difference; negative when `end` is in an earlier month.
    """
    return (end.year - start.year) * 12 + (end.month - start.month)


def months_left(due_on: date, anchor: date) -> int:
    """Return the contributions left before a due date, counting this month.

    Args:
        due_on: The fund's due date.
        anchor: The day to count from.

    Returns:
        0 once the due date has passed, otherwise the months to it plus one.
    """
    if due_on < anchor:
        return 0
    return max(0, months_between(anchor, due_on)) + 1


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


def as_schema(fund: SinkingFundModel, anchor: date) -> SinkingFund:
    """Build a fund's response with its derived figures as of a day.

    Args:
        fund: The fund row, with its contributions.
        anchor: The day the figures are computed for.

    Returns:
        The fund; past its due date with money owed, `per_month` is the whole
        remainder.
    """
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
    """Return the user's sinking funds, earliest due first.

    Args:
        db: Open database session.
        user_id: Whose funds.
        include_archived: Also return archived funds.
        on_day: The day the figures are computed for; defaults to the user's
            today.

    Returns:
        The funds; None when the user does not exist.
    """
    if not user_exists(db, user_id):
        return None

    query = db.query(SinkingFundModel).filter(SinkingFundModel.user_id == user_id)
    if not include_archived:
        query = query.filter(SinkingFundModel.archived.is_(False))

    anchor = on_day or user_today(db, user_id)
    funds = query.order_by(SinkingFundModel.due_on).all()
    return [as_schema(fund, anchor) for fund in funds]


def get_fund(db: Session, user_id: uuid.UUID, fund_id: uuid.UUID):
    """Return the user's fund row with this id, or None.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        fund_id: The fund to fetch.

    Returns:
        The fund row, or None when it is missing or another user's.
    """
    return (
        db.query(SinkingFundModel)
        .filter(SinkingFundModel.id == fund_id, SinkingFundModel.user_id == user_id)
        .first()
    )


def check_accounts(db: Session, user_id: uuid.UUID, from_id, to_id) -> None:
    """Refuse a fund whose two accounts are the same or not both the user's.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        from_id: Account the contributions leave.
        to_id: Account the contributions arrive in.

    Raises:
        ValueError: If the accounts are the same, or either is not the user's.
    """
    if from_id == to_id:
        raise ValueError("Money has to move between two different accounts")
    if owned_account(db, user_id, from_id) is None:
        raise ValueError("That source account does not exist")
    if owned_account(db, user_id, to_id) is None:
        raise ValueError("That destination account does not exist")


def create_fund(
    db: Session, user_id: uuid.UUID, data: SinkingFundCreate, on_day: date | None = None
):
    """Create a sinking fund for the user.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose fund.
        data: The fund; the name is stripped and the target rounded to cents.
        on_day: The day the figures are computed for; defaults to the user's
            today.

    Returns:
        The new fund; None when the user does not exist.

    Raises:
        ValueError: If the accounts are the same or not both the user's.
    """
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
    return as_schema(fund, on_day or user_today(db, user_id))


def update_fund(
    db: Session,
    user_id: uuid.UUID,
    fund_id: uuid.UUID,
    data: SinkingFundUpdate,
    on_day: date | None = None,
):
    """Change the fields sent on one of the user's funds.

    The monthly figure follows on the read; nothing is recalculated or stored.
    Commits.

    Args:
        db: Open database session.
        user_id: Whose fund.
        fund_id: The fund.
        data: The fields to change.
        on_day: The day the figures are computed for; defaults to the user's
            today.

    Returns:
        The updated fund; None when it is not the user's.

    Raises:
        ValueError: If the accounts would be the same or not both the user's.
    """
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
    return as_schema(fund, on_day or user_today(db, user_id))


def transfer_rows(
    db: Session,
    user_id: uuid.UUID,
    fund: SinkingFundModel,
    amount: float,
    occurred_on: date,
    group_id: uuid.UUID,
) -> list[TransactionModel]:
    """Build, unsaved, the two transfer rows a contribution writes.

    Built here rather than through the transfer service, which commits, so the
    transfer and the contribution land in one transaction.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        fund: The fund, naming both accounts.
        amount: Dollars to move, positive.
        occurred_on: The transfer's date.
        group_id: The id tying the two rows together.

    Returns:
        The outgoing and incoming rows.

    Raises:
        ValueError: If either account no longer belongs to the user.
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
    """Set money aside for a fund, writing the transfer and the contribution together.

    The month funded is the month of `occurred_on` (default today); the amount
    defaults to `per_month` and is capped at what remains. Commits.

    Args:
        db: Open database session.
        user_id: Whose fund.
        fund_id: The fund.
        data: The optional amount and date.

    Returns:
        The fund as of the contribution's date; None when it is not the user's.

    Raises:
        ValueError: If that month is already funded, the target is reached, there
            is nothing to set aside, or an account is gone.
    """
    fund = get_fund(db, user_id, fund_id)
    if fund is None:
        return None

    anchor = data.occurred_on or user_today(db, user_id)
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
    """Delete the ledger rows a contribution's transfer wrote, if it has a group.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        group_id: The contribution's transfer group; None does nothing.
    """
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
    """Take back one contribution, deleting its transfer with it.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose fund.
        fund_id: The fund.
        contribution_id: The contribution.
        on_day: The day the figures are computed for; defaults to the user's
            today.

    Returns:
        The fund; None when the fund or contribution is not the user's.
    """
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
    return as_schema(fund, on_day or user_today(db, user_id))


def delete_fund(
    db: Session, user_id: uuid.UUID, fund_id: uuid.UUID, on_day: date | None = None
):
    """Delete a fund, its contributions and the transfers they wrote.

    Archiving is the way to keep the history. Commits.

    Args:
        db: Open database session.
        user_id: Whose fund.
        fund_id: The fund.
        on_day: The day the figures are computed for; defaults to the user's
            today.

    Returns:
        A copy of the deleted fund; None when it is not the user's.
    """
    fund = get_fund(db, user_id, fund_id)
    if fund is None:
        return None

    removed = as_schema(fund, on_day or user_today(db, user_id))
    for contribution in list(fund.contributions or []):
        clear_transfer(db, user_id, contribution.group_id)

    db.delete(fund)
    db.commit()
    return removed


def unfunded_total(db: Session, user_id: uuid.UUID, anchor: date) -> float:
    """Return this month's promised but unmade contributions, for safe-to-spend.

    Sums `unfunded_this_month` over unarchived funds whose source account counts.

    Args:
        db: Open database session.
        user_id: Whose funds.
        anchor: The day that decides which month is "this month".

    Returns:
        The total in dollars, rounded to cents.
    """
    funds = (
        db.query(SinkingFundModel)
        .filter(
            SinkingFundModel.user_id == user_id,
            SinkingFundModel.archived.is_(False),
            # Paid from an unticked account, it is no claim on what counts (D39).
            SinkingFundModel.from_account_id.notin_(uncounted_accounts(user_id)),
        )
        .all()
    )
    return money(sum(as_schema(fund, anchor).unfunded_this_month for fund in funds))
