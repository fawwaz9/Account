import uuid
from calendar import monthrange
from datetime import date

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app._database.models import (
    AccountModel,
    BudgetTargetModel,
    CategoryBudgetModel,
    SpendCategoryModel,
    TransactionModel,
    UserModel,
)
from app.Finances.schemas.budget import (
    AccountBudget,
    BudgetSummary,
    BudgetTargetUpsert,
    CategoryLimitUpsert,
    CategorySpend,
    SpendCategoryCreate,
    SpendCategoryUpdate,
    first_of_month,
)
from app.Finances.utils.limits import effective_limit
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

    update_data = data.model_dump(exclude_unset=True)

    # `create_category` has always checked this and rename never did, because
    # until categories became editable there was no way to reach it. Two faults
    # sit behind it, and the case-insensitive comparison is what closes both:
    #
    #   * `uq_spend_categories_user_name` is case-SENSITIVE, so renaming
    #     "Transport" to "groceries" beside an existing "Groceries" passes the
    #     index and leaves two categories the student cannot tell apart;
    #   * an exact-case collision does hit the index, and the IntegrityError
    #     escapes the route's ValueError handler as a 500 -- the same shape as
    #     the concurrent-registration bug in the audit's low tier.
    new_name = update_data.get("name")
    if new_name is not None:
        clash = (
            db.query(SpendCategoryModel)
            .filter(
                SpendCategoryModel.user_id == user_id,
                SpendCategoryModel.id != category_id,
                SpendCategoryModel.name.ilike(new_name),
            )
            .first()
        )
        if clash:
            raise ValueError("A category with that name already exists")

    for key, value in update_data.items():
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


def set_category_limit(db: Session, user_id: uuid.UUID, data: CategoryLimitUpsert) -> bool:
    """Override one category's limit for one month, or clear the override.

    Returns False when the category is not this user's, which the route maps to
    a 404 -- the same answer as "does not exist", deliberately, so the API does
    not confirm which ids are real.

    A `limit_amount` of None **deletes the row**, so the month falls back to the
    standing limit. That is the only way back: leaving a row behind holding the
    same number as the standing limit would look identical today and stop
    tracking it the moment the standing limit changed, which is exactly the bug
    that makes a "default" not a default.
    """
    category = (
        db.query(SpendCategoryModel)
        .filter(
            SpendCategoryModel.id == data.category_id,
            SpendCategoryModel.user_id == user_id,
        )
        .first()
    )
    if category is None:
        return False

    override = (
        db.query(CategoryBudgetModel)
        .filter(
            CategoryBudgetModel.user_id == user_id,
            CategoryBudgetModel.category_id == data.category_id,
            CategoryBudgetModel.month == data.month,
        )
        .first()
    )

    if data.limit_amount is None:
        if override is not None:
            db.delete(override)
    elif override is None:
        db.add(CategoryBudgetModel(
            id=uuid.uuid4(),
            user_id=user_id,
            category_id=data.category_id,
            month=data.month,
            limit_amount=data.limit_amount,
        ))
    else:
        override.limit_amount = data.limit_amount

    db.commit()
    return True


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
    categories = (
        db.query(SpendCategoryModel)
        .filter(SpendCategoryModel.user_id == user_id)
        .all()
    )
    names = {category.id: category.name for category in categories}
    standing = {category.id: category.monthly_limit for category in categories}
    archived = {category.id for category in categories if category.archived}

    # Only the months that were overridden have rows; a category budgeted the
    # same all year has none, which is what makes the standing limit standing.
    overrides = {
        row.category_id: row.limit_amount
        for row in db.query(CategoryBudgetModel)
        .filter(CategoryBudgetModel.user_id == user_id, CategoryBudgetModel.month == start)
        .all()
    }

    spent_by_category = {
        category_id: round(abs(total or 0.0), 2) for category_id, total in category_rows
    }

    # The union, and the reason for it: a limit you are safely under would
    # otherwise be invisible, because this list was built from spending alone.
    # You could only ever see the limits you were already breaking. Archived
    # categories are excluded unless they have spending this month -- they are
    # history, and a limit on one is not a plan.
    limited = {
        category.id
        for category in categories
        if not category.archived
        and effective_limit(standing.get(category.id), overrides.get(category.id)) is not None
    }

    by_category = []
    for category_id in spent_by_category.keys() | limited:
        spent = spent_by_category.get(category_id, 0.0)
        # Uncategorised has no row, so no limit: `.get` on both sides returns
        # None and `effective_limit` agrees.
        limit = effective_limit(standing.get(category_id), overrides.get(category_id))
        by_category.append(CategorySpend(
            category_id=category_id,
            category_name=names.get(category_id, "Uncategorised"),
            actual=spent,
            limit=limit,
            remaining=round(limit - spent, 2) if limit is not None else 0.0,
            # Mirrors AccountBudget: a limit of 0 gives 0.0 rather than dividing,
            # and the client shows the row as over on `remaining` instead.
            used_percent=round(spent / limit * 100, 1) if limit else 0.0,
            limit_is_override=category_id in overrides,
        ))

    # Unchanged sort, so the existing order is untouched and the rows that are
    # new here -- a limit with nothing spent against it yet -- settle at the end.
    by_category.sort(key=lambda entry: entry.actual, reverse=True)

    return BudgetSummary(
        month=start,
        total_planned=round(sum(entry.planned for entry in entries), 2),
        total_actual=round(sum(entry.actual for entry in entries), 2),
        accounts=entries,
        by_category=by_category,
    )
