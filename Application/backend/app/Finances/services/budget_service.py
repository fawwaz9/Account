"""Service functions for spending categories, monthly targets, limits and the budget.

Categories say what money went on, separately from which account paid. Targets
and per-account category limits say what an account means to spend in a month,
and `get_budget_summary` sets them against what actually went out.
"""

import uuid
from calendar import monthrange
from datetime import date

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app._database.models import (
    AccountCategoryLimitModel,
    AccountCategoryMonthLimitModel,
    AccountModel,
    BudgetTargetModel,
    RecurringTransactionModel,
    SpendCategoryModel,
    TransactionModel,
    UserModel,
)
from app.Finances.schemas.budget import (
    AccountBudget,
    AccountCategoryLimitUpsert,
    BudgetSummary,
    BudgetTargetUpsert,
    CategorySpend,
    SpendCategoryCreate,
    SpendCategoryUpdate,
    first_of_month,
)
from app.Finances.utils.limits import effective_category_limit, planned_for_account
from app.Finances.schemas.transaction import TransactionKind
from app.Finances.services.counted import on_counted_accounts

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
    """Return the first and last day of the month a date falls in.

    Args:
        month: Any date in the month.

    Returns:
        The month's first and last day, both inclusive.
    """
    start = first_of_month(month)
    return start, start.replace(day=monthrange(start.year, start.month)[1])


# --------------------------------------------------------------- categories --

def get_categories(db: Session, user_id: uuid.UUID, include_archived: bool = False):
    """Return the user's spending categories, seeding the defaults on first read.

    A user with no categories at all gets `DEFAULT_CATEGORIES` written (and
    committed) before the list is returned.

    Args:
        db: Open database session.
        user_id: Whose categories.
        include_archived: Also return archived categories.

    Returns:
        The categories by position, then name; None when the user does not
        exist.
    """
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
    """Create a spending category for the user.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose category.
        data: The category.

    Returns:
        The new category; None when the user does not exist.

    Raises:
        ValueError: If the user already has a category of that name, ignoring
            case.
    """
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
    """Rename, archive or reorder one of the user's categories.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose category.
        category_id: The category.
        data: The fields to change.

    Returns:
        The updated category; None when it is not the user's.

    Raises:
        ValueError: If another of the user's categories already has the new name,
            ignoring case.
    """
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
    """Delete one of the user's categories, keeping the money it labelled.

    Its limits on every account are deleted, and its transactions and standing
    instructions become uncategorised. Commits.

    Args:
        db: Open database session.
        user_id: Whose category.
        category_id: The category.

    Returns:
        The deleted category row; None when it is not the user's.
    """
    category = (
        db.query(SpendCategoryModel)
        .filter(SpendCategoryModel.id == category_id, SpendCategoryModel.user_id == user_id)
        .first()
    )
    if category is None:
        return None

    # Any limits set against this category, on any account. A foreign key, so
    # leaving them behind fails the delete rather than merely littering.
    db.query(AccountCategoryLimitModel).filter(
        AccountCategoryLimitModel.user_id == user_id,
        AccountCategoryLimitModel.category_id == category_id,
    ).delete(synchronize_session=False)

    db.query(AccountCategoryMonthLimitModel).filter(
        AccountCategoryMonthLimitModel.user_id == user_id,
        AccountCategoryMonthLimitModel.category_id == category_id,
    ).delete(synchronize_session=False)

    # Scoped to the owner: without the user_id filter this UPDATE reaches every
    # row carrying the id, including other people's.
    db.query(TransactionModel).filter(
        TransactionModel.category_id == category_id,
        TransactionModel.user_id == user_id,
    ).update({TransactionModel.category_id: None}, synchronize_session=False)
    # Standing instructions too, the same way: the rule keeps running and its
    # future rows arrive uncategorised. Missing, and every category a recurring
    # rule used could not be deleted -- the foreign key refused, as a 500.
    db.query(RecurringTransactionModel).filter(
        RecurringTransactionModel.category_id == category_id,
        RecurringTransactionModel.user_id == user_id,
    ).update({RecurringTransactionModel.category_id: None}, synchronize_session=False)
    db.delete(category)
    db.commit()
    return category


# ------------------------------------------------------------------ targets --

def set_target(db: Session, user_id: uuid.UUID, data: BudgetTargetUpsert):
    """Create or replace one account's planned spending for one month.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose account.
        data: The account, month (already the first) and amount.

    Returns:
        The target row; None when the account is not the user's.
    """
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


def set_account_category_limit(
    db: Session, user_id: uuid.UUID, data: AccountCategoryLimitUpsert
) -> bool:
    """Set or clear what one account may spend on one category.

    With no month the standing limit is written; with a month, that month's
    override. A null amount deletes the row (no limit), which is different from a
    limit of 0. Commits.

    Args:
        db: Open database session.
        user_id: Whose account and category.
        data: The pair, the optional month and the amount.

    Returns:
        True when written; False when the account or category is not the user's,
        which the route answers as a 404.
    """
    account = (
        db.query(AccountModel)
        .filter(AccountModel.id == data.account_id, AccountModel.user_id == user_id)
        .first()
    )
    if account is None:
        return False

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

    # Two tables, chosen by whether a month was named. A month writes that
    # month's override and leaves the standing figure alone; no month writes the
    # standing figure and leaves every override alone.
    if data.month is None:
        row = (
            db.query(AccountCategoryLimitModel)
            .filter(
                AccountCategoryLimitModel.user_id == user_id,
                AccountCategoryLimitModel.account_id == data.account_id,
                AccountCategoryLimitModel.category_id == data.category_id,
            )
            .first()
        )
        if data.limit_amount is None:
            if row is not None:
                db.delete(row)
        elif row is None:
            db.add(AccountCategoryLimitModel(
                id=uuid.uuid4(),
                user_id=user_id,
                account_id=data.account_id,
                category_id=data.category_id,
                limit_amount=data.limit_amount,
            ))
        else:
            row.limit_amount = data.limit_amount
    else:
        row = (
            db.query(AccountCategoryMonthLimitModel)
            .filter(
                AccountCategoryMonthLimitModel.user_id == user_id,
                AccountCategoryMonthLimitModel.account_id == data.account_id,
                AccountCategoryMonthLimitModel.category_id == data.category_id,
                AccountCategoryMonthLimitModel.month == data.month,
            )
            .first()
        )
        if data.limit_amount is None:
            # Deleted, not zeroed. A row holding the standing figure would look
            # identical today and stop following it the moment it changed.
            if row is not None:
                db.delete(row)
        elif row is None:
            db.add(AccountCategoryMonthLimitModel(
                id=uuid.uuid4(),
                user_id=user_id,
                account_id=data.account_id,
                category_id=data.category_id,
                month=data.month,
                limit_amount=data.limit_amount,
            ))
        else:
            row.limit_amount = data.limit_amount

    db.commit()
    return True


# ------------------------------------------------------------------ summary --

def get_budget_summary(db: Session, user_id: uuid.UUID, month: date):
    """Return one month's planned and actual spending across counted accounts.

    Each counted, unarchived account's plan is the sum of its category limits for
    the month when it has any (overrides included), else its target; its actual is
    expenses plus outgoing transfer legs. Categories total expenses on counted
    accounts, with no limits attached.

    Args:
        db: Open database session.
        user_id: Whose budget.
        month: Any day of the month.

    Returns:
        The month's summary; None when the user does not exist.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None

    start, end = month_bounds(month)
    accounts = (
        db.query(AccountModel)
        .filter(
            AccountModel.user_id == user_id,
            AccountModel.archived.is_(False),
            AccountModel.counts_toward_net_worth.is_(True),  # D39
        )
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

    # One query for every account's category limits, grouped here, rather than
    # one per account inside the loop below.
    standing_by_account: dict[uuid.UUID, dict[uuid.UUID, float]] = {}
    for row in (
        db.query(AccountCategoryLimitModel)
        .filter(AccountCategoryLimitModel.user_id == user_id)
        .all()
    ):
        standing_by_account.setdefault(row.account_id, {})[row.category_id] = row.limit_amount

    # Resolved for *this* month, so the budget page's total matches the account
    # page's for the month on screen rather than for a typical one.
    overrides_by_account: dict[uuid.UUID, dict[uuid.UUID, float]] = {}
    for row in (
        db.query(AccountCategoryMonthLimitModel)
        .filter(
            AccountCategoryMonthLimitModel.user_id == user_id,
            AccountCategoryMonthLimitModel.month == start,
        )
        .all()
    ):
        overrides_by_account.setdefault(row.account_id, {})[row.category_id] = row.limit_amount

    limits_by_account: dict[uuid.UUID, list[float]] = {}
    for account_id in standing_by_account.keys() | overrides_by_account.keys():
        st = standing_by_account.get(account_id, {})
        ov = overrides_by_account.get(account_id, {})
        limits_by_account[account_id] = [
            effective_category_limit(st.get(cid), ov.get(cid))
            for cid in st.keys() | ov.keys()
        ]

    entries = []
    for account in sorted(accounts, key=lambda a: (a.position, a.name)):
        # The same rule the account page uses, from the same function, so the
        # two screens cannot report different targets for one account.
        plan, is_derived = planned_for_account(
            limits_by_account.get(account.id, []),
            round(planned.get(account.id, 0.0), 2),
        )
        spent = round(actual.get(account.id, 0.0), 2)
        entries.append(AccountBudget(
            account_id=account.id,
            account_name=account.name,
            planned=plan,
            actual=spent,
            remaining=round(plan - spent, 2),
            used_percent=round(spent / plan * 100, 1) if plan > 0 else 0.0,
            planned_is_derived=is_derived,
        ))

    category_rows = (
        db.query(TransactionModel.category_id, func.sum(TransactionModel.amount))
        .filter(
            TransactionModel.user_id == user_id,
            TransactionModel.kind == TransactionKind.EXPENSE.value,
            TransactionModel.occurred_on >= start,
            TransactionModel.occurred_on <= end,
            on_counted_accounts(user_id),  # D39
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
