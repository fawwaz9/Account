"""One account's month, composed server-side.

Kept apart from `account_service` because it answers a different question: that
module is about the pots themselves, this one is about what moved through one
of them.
"""
import uuid
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app._database.models import (
    AccountModel,
    BudgetTargetModel,
    SpendCategoryModel,
    TransactionModel,
)
from app.Finances.schemas.account import AccountActivity, BalancePoint, DayFlow
from app.Finances.schemas.budget import CategorySpend
from app.Finances.services.budget_service import month_bounds
from app.Finances.schemas.transaction import TransactionKind


def is_money_out(kind: str, amount: float) -> bool:
    """Money that has left the account.

    Deliberately the same rule the planned-spend bars use: an expense, or the
    outgoing leg of a transfer. If these two ever disagree the account page and
    the budget page will report different numbers for the same month.
    """
    return kind == TransactionKind.EXPENSE.value or (
        kind == TransactionKind.TRANSFER.value and amount < 0
    )


def is_money_in(kind: str, amount: float) -> bool:
    """The mirror of `is_money_out`: income, or the receiving leg of a transfer."""
    return kind == TransactionKind.INCOME.value or (
        kind == TransactionKind.TRANSFER.value and amount > 0
    )


def running_balance(db: Session, account_id: uuid.UUID) -> list[BalancePoint]:
    """The account's balance after each day it moved, from the very first row.

    Grouped in SQL and accumulated here, so a long history costs one query and
    one pass rather than a row per point.
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

    # No `limit` here, deliberately, so the shared "Where it went" section draws
    # no bars on this page. A category limit spans every account; judging it
    # against one account's share of the spending would answer a question nobody
    # asked and look authoritative doing it. The client needs no flag for this --
    # a row with no limit renders exactly as it did before limits existed.
    by_category = sorted(
        (
            CategorySpend(
                category_id=category_id,
                category_name=names.get(category_id, "Uncategorised"),
                actual=round(actual, 2),
            )
            for category_id, actual in per_category.items()
        ),
        key=lambda entry: entry.actual,
        reverse=True,
    )

    target = (
        db.query(BudgetTargetModel)
        .filter(
            BudgetTargetModel.user_id == user_id,
            BudgetTargetModel.account_id == account_id,
            BudgetTargetModel.month == start,
        )
        .first()
    )
    planned = round(target.planned_amount if target else 0.0, 2)
    spent = round(total_out, 2)

    balance = (
        db.query(func.sum(TransactionModel.amount))
        .filter(TransactionModel.account_id == account_id)
        .scalar()
    )

    return AccountActivity(
        account_id=account.id,
        account_name=account.name,
        month=start,
        balance=round(balance or 0.0, 2),
        total_in=round(total_in, 2),
        total_out=spent,
        net=round(total_in - total_out, 2),
        transaction_count=len(rows),
        planned=planned,
        remaining=round(planned - spent, 2),
        used_percent=round(spent / planned * 100, 1) if planned > 0 else 0.0,
        daily=[flows[key] for key in sorted(flows)],
        by_category=by_category,
        balance_history=running_balance(db, account_id),
    )
