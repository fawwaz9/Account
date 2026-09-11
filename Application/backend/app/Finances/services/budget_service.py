import uuid
from calendar import monthrange
from datetime import date

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app._database.models import (
    AccountModel,
    BudgetTargetModel,
    SpendCategoryModel,
    TransactionModel,
    UserModel,
)
from app.Finances.schemas.budget import (
    AccountBudget,
    BudgetSummary,
    BudgetTargetUpsert,
    CategorySpend,
    SpendCategoryCreate,
    SpendCategoryUpdate,
    first_of_month,
)
from app.Finances.schemas.transaction import TransactionKind

#: Seeded once so the first expense has somewhere to go.
DEFAULT_CATEGORIES = [
    "Groceries",
    "Sports",
    "Health/medical",
    "Home",
    "Transportation",
    "Personal",
    "Eating out",
    "Utilities",
    "Gifts",
    "Debt",
    "Technology",
    "Charity",
    "Investments",
    "School fees",
]


def month_bounds(month: date) -> tuple[date, date]:
    start = first_of_month(month)
    return start, start.replace(day=monthrange(start.year, start.month)[1])


# --------------------------------------------------------------- categories --

def get_categories(db: Session, user_id: uuid.UUID, include_archived: bool = False):
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None

    categories = (
        db.query(SpendCategoryModel).filter(SpendCategoryModel.user_id == user_id).all()
    )
    if not categories:
        categories = [
            SpendCategoryModel(id=uuid.uuid4(), user_id=user_id, name=name, position=index)
            for index, name in enumerate(DEFAULT_CATEGORIES)
        ]
        db.add_all(categories)
        db.commit()
        for category in categories:
            db.refresh(category)

    if not include_archived:
        categories = [category for category in categories if not category.archived]

    categories.sort(key=lambda category: (category.position, category.name))
    return categories


def create_category(db: Session, user_id: uuid.UUID, data: SpendCategoryCreate):
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None

    clash = (
        db.query(SpendCategoryModel)
        .filter(SpendCategoryModel.user_id == user_id, SpendCategoryModel.name.ilike(data.name))
        .first()
    )
    if clash:
        raise ValueError("A category with that name already exists")

    category = SpendCategoryModel(
        id=uuid.uuid4(),
        user_id=user_id,
        name=data.name,
        archived=data.archived,
        position=data.position,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def update_category(db: Session, user_id: uuid.UUID, category_id: uuid.UUID, data: SpendCategoryUpdate):
    category = (
        db.query(SpendCategoryModel)
        .filter(SpendCategoryModel.id == category_id, SpendCategoryModel.user_id == user_id)
        .first()
    )
    if category is None:
        return None

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(category, key, value)

    db.commit()
    db.refresh(category)
    return category


def delete_category(db: Session, user_id: uuid.UUID, category_id: uuid.UUID):
    """Detaches the category from its transactions rather than deleting them.

    A category is a label on an expense, not the expense itself -- removing the
    label must not remove the money.
    """
    category = (
        db.query(SpendCategoryModel)
        .filter(SpendCategoryModel.id == category_id, SpendCategoryModel.user_id == user_id)
        .first()
    )
    if category is None:
        return None

    # Scoped to the owner: without the user_id filter this UPDATE reaches every
    # row carrying the id, including other people's.
    db.query(TransactionModel).filter(
        TransactionModel.category_id == category_id,
        TransactionModel.user_id == user_id,
    ).update({TransactionModel.category_id: None}, synchronize_session=False)
    db.delete(category)
    db.commit()
    return category


# ------------------------------------------------------------------ targets --

def set_target(db: Session, user_id: uuid.UUID, data: BudgetTargetUpsert):
    """One target per account per month, created or replaced."""
    account = (
        db.query(AccountModel)
        .filter(AccountModel.id == data.account_id, AccountModel.user_id == user_id)
        .first()
    )
    if account is None:
        return None

    target = (
        db.query(BudgetTargetModel)
        .filter(
            BudgetTargetModel.user_id == user_id,
            BudgetTargetModel.account_id == data.account_id,
            BudgetTargetModel.month == data.month,
        )
        .first()
    )

    if target is None:
        target = BudgetTargetModel(
            id=uuid.uuid4(),
            user_id=user_id,
            account_id=data.account_id,
            month=data.month,
            planned_amount=data.planned_amount,
        )
        db.add(target)
    else:
        target.planned_amount = data.planned_amount

    db.commit()
    db.refresh(target)
    return target


# ------------------------------------------------------------------ summary --

def get_budget_summary(db: Session, user_id: uuid.UUID, month: date):
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None

    start, end = month_bounds(month)
    accounts = (
        db.query(AccountModel)
        .filter(AccountModel.user_id == user_id, AccountModel.archived.is_(False))
        .all()
    )

    planned = {
        row.account_id: row.planned_amount
        for row in db.query(BudgetTargetModel)
        .filter(BudgetTargetModel.user_id == user_id, BudgetTargetModel.month == start)
        .all()
    }

    # Expenses, plus the outgoing half of a transfer: money moved out of a pot
    # has left it just as surely as money spent from it, so a target that
    # ignored transfers would quietly under-report. Only the negative leg
    # counts -- the matching positive leg lands on the receiving account, where
    # it is money arriving, not spending.
    spend_rows = (
        db.query(TransactionModel.account_id, func.sum(TransactionModel.amount))
        .filter(
            TransactionModel.user_id == user_id,
            TransactionModel.occurred_on >= start,
            TransactionModel.occurred_on <= end,
            or_(
                TransactionModel.kind == TransactionKind.EXPENSE.value,
                and_(
                    TransactionModel.kind == TransactionKind.TRANSFER.value,
                    TransactionModel.amount < 0,
                ),
            ),
        )
        .group_by(TransactionModel.account_id)
        .all()
    )
    actual = {account_id: abs(total or 0.0) for account_id, total in spend_rows}

    entries = []
    for account in sorted(accounts, key=lambda a: (a.position, a.name)):
        plan = round(planned.get(account.id, 0.0), 2)
        spent = round(actual.get(account.id, 0.0), 2)
        entries.append(AccountBudget(
            account_id=account.id,
            account_name=account.name,
            planned=plan,
            actual=spent,
            remaining=round(plan - spent, 2),
            used_percent=round(spent / plan * 100, 1) if plan > 0 else 0.0,
        ))

    category_rows = (
        db.query(TransactionModel.category_id, func.sum(TransactionModel.amount))
        .filter(
            TransactionModel.user_id == user_id,
            TransactionModel.kind == TransactionKind.EXPENSE.value,
            TransactionModel.occurred_on >= start,
            TransactionModel.occurred_on <= end,
        )
        .group_by(TransactionModel.category_id)
        .all()
    )
    names = {
        category.id: category.name
        for category in db.query(SpendCategoryModel)
        .filter(SpendCategoryModel.user_id == user_id)
        .all()
    }
    by_category = sorted(
        (
            CategorySpend(
                category_id=category_id,
                category_name=names.get(category_id, "Uncategorised"),
                actual=round(abs(total or 0.0), 2),
            )
            for category_id, total in category_rows
        ),
        key=lambda entry: entry.actual,
        reverse=True,
    )

    return BudgetSummary(
        month=start,
        total_planned=round(sum(entry.planned for entry in entries), 2),
        total_actual=round(sum(entry.actual for entry in entries), 2),
        accounts=entries,
        by_category=by_category,
    )
