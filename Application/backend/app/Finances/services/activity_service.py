"""Service functions for one account's month, composed server-side for its page.

Kept apart from `account_service`, which is about the accounts themselves; this
is about what moved through one of them. The money-in and money-out rule here
must match the budget page's, or the two pages report different numbers.
"""
import uuid
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app._database.models import (
    AccountModel,
    AccountCategoryLimitModel,
    AccountCategoryMonthLimitModel,
    BudgetTargetModel,
    SpendCategoryModel,
    TransactionModel,
)
from app.Finances.schemas.account import (
    AccountActivity,
    AccountKind,
    BalancePoint,
    DayFlow,
)
from app.Finances.schemas.budget import CategorySpend
from app.Finances.services.account_service import (
    build_investment_return,
    ledger_balance_as_of,
    measured_on,
    readings_for_account,
)
from app.Finances.services.budget_service import month_bounds
from app.shared.dates import user_today
from app.Finances.utils.limits import effective_category_limit, planned_for_account
from app.Finances.schemas.transaction import TransactionKind


def is_money_out(kind: str, amount: float) -> bool:
    """Return whether a row is money leaving its account.

    Args:
        kind: The row's kind.
        amount: The row's signed amount.

    Returns:
        True for an expense, or a transfer with a negative amount.
    """
    return kind == TransactionKind.EXPENSE.value or (
        kind == TransactionKind.TRANSFER.value and amount < 0
    )


def is_money_in(kind: str, amount: float) -> bool:
    """Return whether a row is money arriving: income or an incoming transfer leg.

    Args:
        kind: The row's kind.
        amount: The row's signed amount.

    Returns:
        True for income, or a transfer with a positive amount.
    """
    return kind == TransactionKind.INCOME.value or (
        kind == TransactionKind.TRANSFER.value and amount > 0
    )


def running_balance(db: Session, account_id: uuid.UUID) -> list[BalancePoint]:
    """Return an account's balance after each day it moved, from its first row.

    Grouped by day in SQL and accumulated here, so a long history is one query.

    Args:
        db: Open database session.
        account_id: The account; the caller has already checked it is the user's.

    Returns:
        One point per day with movement, oldest first.
    """
    rows = (
        db.query(TransactionModel.occurred_on, func.sum(TransactionModel.amount))
        .filter(TransactionModel.account_id == account_id)
        .group_by(TransactionModel.occurred_on)
        .order_by(TransactionModel.occurred_on.asc())
        .all()
    )

    history: list[BalancePoint] = []
    total = 0.0
    for day, change in rows:
        total += change or 0.0
        history.append(BalancePoint(day=day, balance=round(total, 2)))
    return history


def get_account_activity(
    db: Session,
    user_id: uuid.UUID,
    account_id: uuid.UUID,
    month: date,
) -> AccountActivity | None:
    """Return everything one account's page shows for a month.

    Money in and out follow `is_money_in` and `is_money_out`; category spending is
    expenses only, with every category this account limits listed even when nothing
    was spent. An investment account also gets its reading for the month and its
    all-time return.

    Args:
        db: Open database session.
        user_id: Whose account.
        account_id: The account.
        month: Any day of the month to show.

    Returns:
        The month's activity; None when the account is not the user's.
    """
    account = (
        db.query(AccountModel)
        .filter(AccountModel.id == account_id, AccountModel.user_id == user_id)
        .first()
    )
    if account is None:
        return None

    start, end = month_bounds(month)

    rows = (
        db.query(TransactionModel)
        .filter(
            TransactionModel.user_id == user_id,
            TransactionModel.account_id == account_id,
            TransactionModel.occurred_on >= start,
            TransactionModel.occurred_on <= end,
        )
        .all()
    )

    # Every day of the month, so a quiet week reads as a gap in the calendar
    # rather than being squeezed out of the axis.
    flows: dict[date, DayFlow] = {}
    day = start
    while day <= end:
        flows[day] = DayFlow(day=day, money_in=0.0, money_out=0.0)
        day += timedelta(days=1)

    total_in = 0.0
    total_out = 0.0
    for row in rows:
        entry = flows[row.occurred_on]
        if is_money_out(row.kind, row.amount):
            magnitude = abs(row.amount)
            entry.money_out += magnitude
            total_out += magnitude
        elif is_money_in(row.kind, row.amount):
            entry.money_in += row.amount
            total_in += row.amount

    for entry in flows.values():
        entry.money_in = round(entry.money_in, 2)
        entry.money_out = round(entry.money_out, 2)

    # Expenses only, matching the budget page's breakdown. Transfers carry no
    # category, so including them would pile the whole month into one
    # "Uncategorised" row and drown the real labels.
    names = {
        category.id: category.name
        for category in db.query(SpendCategoryModel)
        .filter(SpendCategoryModel.user_id == user_id)
        .all()
    }
    per_category: dict[uuid.UUID | None, float] = {}
    for row in rows:
        if row.kind != TransactionKind.EXPENSE.value:
            continue
        per_category[row.category_id] = per_category.get(row.category_id, 0.0) + abs(row.amount)

    # What this account means to spend, per category. Keyed on the pair, so the
    # limit and the spending below cover the same money -- which is the thing
    # the whole-budget version got wrong.
    standing = {
        row.category_id: row.limit_amount
        for row in db.query(AccountCategoryLimitModel)
        .filter(
            AccountCategoryLimitModel.user_id == user_id,
            AccountCategoryLimitModel.account_id == account_id,
        )
        .all()
    }
    # Only the months that were overridden have rows here; a category budgeted
    # the same all year has none, which is what makes the standing limit stand.
    overrides = {
        row.category_id: row.limit_amount
        for row in db.query(AccountCategoryMonthLimitModel)
        .filter(
            AccountCategoryMonthLimitModel.user_id == user_id,
            AccountCategoryMonthLimitModel.account_id == account_id,
            AccountCategoryMonthLimitModel.month == start,
        )
        .all()
    }
    limits = {
        cid: effective_category_limit(standing.get(cid), overrides.get(cid))
        for cid in standing.keys() | overrides.keys()
    }

    # A limited category appears even with nothing spent on it here. Built from
    # spending alone, a limit you were safely under would be invisible, and you
    # could only ever see the ones you were already breaking.
    by_category = []
    for category_id in per_category.keys() | limits.keys():
        actual = round(per_category.get(category_id, 0.0), 2)
        # Uncategorised has no row to hang a limit on, so `.get` returns None
        # for it and the row renders as a plain total.
        limit = limits.get(category_id)
        by_category.append(CategorySpend(
            category_id=category_id,
            category_name=names.get(category_id, "Uncategorised"),
            actual=actual,
            limit=limit,
            remaining=round(limit - actual, 2) if limit is not None else 0.0,
            # A limit of 0 divides into nothing, so it reports 0% and the row is
            # shown as over on `remaining` instead.
            used_percent=round(actual / limit * 100, 1) if limit else 0.0,
            limit_is_override=category_id in overrides,
        ))
    by_category.sort(key=lambda entry: entry.actual, reverse=True)

    target = (
        db.query(BudgetTargetModel)
        .filter(
            BudgetTargetModel.user_id == user_id,
            BudgetTargetModel.account_id == account_id,
            BudgetTargetModel.month == start,
        )
        .first()
    )
    # Derived from the categories when there are any, and the figure typed into
    # Planned spend when there are not -- which is what keeps Savings and Money
    # Lent, who carry targets and no categories, reading as budgeted.
    planned, planned_is_derived = planned_for_account(
        [v for v in limits.values() if v is not None],
        round(target.planned_amount if target else 0.0, 2),
    )
    spent = round(total_out, 2)

    balance = (
        db.query(func.sum(TransactionModel.amount))
        .filter(TransactionModel.account_id == account_id)
        .scalar()
    )

    # What an investment is actually worth, for the month on screen -- that
    # month's reading, or the last one taken before it, flagged as carried
    # forward so the page can date it.
    #
    # Gated on kind for two reasons: readings are deliberately left behind when
    # an account stops being an investment, and the dated balance below is a
    # query no other kind of account has any use for.
    investment_return = None
    all_time_return = None
    ledger_at_month = 0.0
    if account.kind == AccountKind.INVESTMENT.value:
        readings = readings_for_account(db, user_id, account_id)
        # The month's own balance, not the all-time one above. The entry form
        # subtracts a typed market value from this, and using today's balance for
        # a past month would subtract every deposit made since.
        ledger_at_month = ledger_balance_as_of(
            db, user_id, account_id, measured_on(start, user_today(db, user_id))
        )
        investment_return = build_investment_return(
            readings, ledger_at_month, for_month=start
        )
        # The same figure the card shows: latest reading, all-time balance. Built
        # from the readings already loaded, so it costs no extra query. Kept apart
        # from the month's figure above because the page header is an all-time
        # number -- deriving it from the month's reading would add March's gain to
        # today's balance the moment anyone stepped the month picker back.
        all_time_return = build_investment_return(readings, round(balance or 0.0, 2))

    return AccountActivity(
        account_id=account.id,
        account_name=account.name,
        month=start,
        kind=account.kind,
        balance=round(balance or 0.0, 2),
        total_in=round(total_in, 2),
        total_out=spent,
        net=round(total_in - total_out, 2),
        transaction_count=len(rows),
        planned=planned,
        remaining=round(planned - spent, 2),
        used_percent=round(spent / planned * 100, 1) if planned > 0 else 0.0,
        planned_is_derived=planned_is_derived,
        daily=[flows[key] for key in sorted(flows)],
        by_category=by_category,
        balance_history=running_balance(db, account_id),
        investment_return=investment_return,
        all_time_return=all_time_return,
        ledger_balance_at_month=ledger_at_month,
    )
