"""Service functions for accounts: the pots, their balances, net worth and readings.

A balance is always the sum of an account's ledger rows, never stored. The last
unarchived spending and savings accounts are protected from deletion, archiving
and re-kinding. An investment account can also carry monthly readings of how far
its holding sits above or below the ledger (see `Finances/utils/returns.py`).
"""

import uuid
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app._database.models import (
    ImportModel,
    AccountCategoryLimitModel,
    AccountCategoryMonthLimitModel,
    AccountModel,
    AccountMonthValueModel,
    BudgetTargetModel,
    RecurringTransactionModel,
    SinkingFundModel,
    TransactionModel,
    UserModel,
)
from app.Finances.schemas.account import (
    DEFAULT_ACCOUNTS,
    PROTECTED_KINDS,
    AccountCreate,
    AccountKind,
    AccountMonthValueUpsert,
    AccountUpdate,
    InvestmentReturn,
    NetWorth,
)
from app.Finances.services.budget_service import month_bounds
from app.Finances.utils.returns import latest_reading, month_gain, return_percent
from app.shared.dates import user_today


def seed_default_accounts(db: Session, user_id: uuid.UUID) -> list[AccountModel]:
    """Write `DEFAULT_ACCOUNTS` for a user who has none, and return them.

    Done lazily on first read rather than at signup. Commits.

    Args:
        db: Open database session.
        user_id: Whose accounts.

    Returns:
        The new account rows, in their seeded order.
    """
    created = [
        AccountModel(
            id=uuid.uuid4(),
            user_id=user_id,
            name=name,
            kind=kind.value,
            income_share=share,
            position=index,
        )
        for index, (name, kind, share) in enumerate(DEFAULT_ACCOUNTS)
    ]
    db.add_all(created)
    db.commit()
    for account in created:
        db.refresh(account)
    return created


#: Why each protected kind matters, said in the refusal rather than left for the
#: student to work out. A message that only says "not allowed" turns a guard
#: into an obstacle; one that says what depends on it is an explanation.
PROTECTED_REASON: dict[str, str] = {
    "spending": "Safe-to-spend reads from it",
    "savings": "the income split needs somewhere to save",
}


def protected_kind_values() -> set[str]:
    """Return the stored values of the kinds the app needs at least one account of.

    Returns:
        The `kind` strings of `PROTECTED_KINDS`.
    """
    return {kind.value for kind in PROTECTED_KINDS}


def would_orphan_role(
    db: Session, user_id: uuid.UUID, account: AccountModel
) -> bool:
    """Return whether taking an account out of service would leave its kind empty.

    Out of service means deleted, archived or given another kind. Only unarchived
    accounts count as survivors, and an account already archived never orphans a
    role.

    Args:
        db: Open database session.
        user_id: Whose accounts.
        account: The account being removed.

    Returns:
        True when it is the last unarchived spending or savings account.
    """
    if account.archived:
        return False
    if account.kind not in protected_kind_values():
        return False

    survivors = (
        db.query(func.count(AccountModel.id))
        .filter(
            AccountModel.user_id == user_id,
            AccountModel.kind == account.kind,
            AccountModel.archived.is_(False),
            AccountModel.id != account.id,
        )
        .scalar()
    )
    return not survivors


def role_refusal(account: AccountModel, verb: str) -> str:
    """Return the message refusing to remove the last account of a protected kind.

    Args:
        account: The account the user tried to remove or re-kind.
        verb: What was attempted, as a gerund ("deleting", "archiving").

    Returns:
        A sentence naming the account and how to proceed.
    """
    reason = PROTECTED_REASON.get(account.kind, "the app depends on it")
    return (
        f"{account.name} is your only {account.kind} account and {reason}. "
        f"Create another {account.kind} account before {verb} this one."
    )


def balances_by_account(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, float]:
    """Return every account's balance in one grouped query.

    Args:
        db: Open database session.
        user_id: Whose ledger.

    Returns:
        Account id to balance, rounded to cents; accounts with no rows are absent.
    """
    rows = (
        db.query(TransactionModel.account_id, func.sum(TransactionModel.amount))
        .filter(TransactionModel.user_id == user_id)
        .group_by(TransactionModel.account_id)
        .all()
    )
    return {account_id: round(total or 0.0, 2) for account_id, total in rows}


def balance_of(db: Session, user_id: uuid.UUID, account_id: uuid.UUID) -> float:
    """Return one account's balance, summed by the database.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        account_id: The account.

    Returns:
        The balance rounded to cents; 0 with no rows.
    """
    total = (
        db.query(func.sum(TransactionModel.amount))
        .filter(
            TransactionModel.user_id == user_id,
            TransactionModel.account_id == account_id,
        )
        .scalar()
    )
    return round(total or 0.0, 2)


def attach_balances(accounts: list[AccountModel], balances: dict[uuid.UUID, float]):
    """Set each account row's `balance` from a lookup; absent accounts get 0.

    Args:
        accounts: Account rows to annotate; mutated in place.
        balances: Balance by account id, in dollars.

    Returns:
        The same list, for chaining.
    """
    for account in accounts:
        account.balance = balances.get(account.id, 0.0)
    return accounts


# ------------------------------------------------- what an investment is worth --

#: One stored reading, as the helpers below pass them around: the month, the
#: level above or below the ledger, and what was typed to produce it.
StoredReading = tuple["date", float, float | None]


def ledger_balance_as_of(
    db: Session, user_id: uuid.UUID, account_id: uuid.UUID, on_date
) -> float:
    """Return an account's balance as it stood at the end of a given day.

    A reading for a past month must be measured against that month's ledger, not
    today's, or later deposits would turn a gain into a loss.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        account_id: The account.
        on_date: The day; rows dated on or before it count.

    Returns:
        The balance, rounded to cents.
    """
    total = (
        db.query(func.sum(TransactionModel.amount))
        .filter(
            TransactionModel.user_id == user_id,
            TransactionModel.account_id == account_id,
            TransactionModel.occurred_on <= on_date,
        )
        .scalar()
    )
    return round(total or 0.0, 2)


def measured_on(month, today: date) -> date:
    """Return the day a month's reading is measured against.

    Args:
        month: Any day of the month.
        today: The user's today.

    Returns:
        The month's last day, or `today` when the month has not finished.
    """
    _, month_end = month_bounds(month)
    return min(month_end, today)


def readings_by_account(
    db: Session, user_id: uuid.UUID
) -> dict[uuid.UUID, list[StoredReading]]:
    """Return every investment reading the user has recorded, grouped by account.

    Args:
        db: Open database session.
        user_id: Whose readings.

    Returns:
        Account id to (month, difference, market value) tuples, in no order.
    """
    rows = (
        db.query(
            AccountMonthValueModel.account_id,
            AccountMonthValueModel.month,
            AccountMonthValueModel.difference_amount,
            AccountMonthValueModel.market_value,
        )
        .filter(AccountMonthValueModel.user_id == user_id)
        .all()
    )

    grouped: dict[uuid.UUID, list[StoredReading]] = {}
    for account_id, month, difference, market in rows:
        grouped.setdefault(account_id, []).append((month, difference, market))
    return grouped


def readings_for_account(
    db: Session, user_id: uuid.UUID, account_id: uuid.UUID
) -> list[StoredReading]:
    """Return one account's readings as (month, difference, market value) tuples.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        account_id: The investment account.

    Returns:
        One tuple per recorded month, in no particular order; empty when none.
    """
    rows = (
        db.query(
            AccountMonthValueModel.month,
            AccountMonthValueModel.difference_amount,
            AccountMonthValueModel.market_value,
        )
        .filter(
            AccountMonthValueModel.user_id == user_id,
            AccountMonthValueModel.account_id == account_id,
        )
        .all()
    )
    return [(month, difference, market) for month, difference, market in rows]


def build_investment_return(
    readings: list[StoredReading], ledger_balance: float, for_month=None
) -> InvestmentReturn | None:
    """Build the investment figure a response carries from an account's readings.

    Args:
        readings: The account's stored readings.
        ledger_balance: The balance the percentage is measured against.
        for_month: The month on screen; its own reading or the last one before it
            applies. None takes the latest reading overall, as the account card
            does.

    Returns:
        The reading that applies, its percentage and, for a month-scoped request,
        the month's movement; None when no reading applies.
    """
    found = latest_reading(
        [(month, difference) for month, difference, _ in readings],
        on_or_before=for_month,
    )
    if found is None:
        return None

    as_of, difference = found
    return InvestmentReturn(
        difference_amount=difference,
        return_percent=return_percent(difference, ledger_balance),
        as_of=as_of,
        is_carried_forward=for_month is not None and as_of < for_month,
        ledger_balance=ledger_balance,
        market_value=next(
            (market for month, _, market in readings if month == as_of), None
        ),
        # Only meaningful for a month-scoped request. The card asks for no month,
        # so it gets None rather than a movement figure it has no month to apply
        # to -- and the pure rule returns None for a carried month anyway.
        month_gain=(
            month_gain(
                [(month, amount) for month, amount, _ in readings], for_month
            )
            if for_month is not None
            else None
        ),
    )


def attach_investment_returns(
    accounts: list[AccountModel],
    readings: dict[uuid.UUID, list[StoredReading]],
    balances: dict[uuid.UUID, float],
):
    """Set each account row's `investment_return`: the latest reading, investments only.

    Readings are kept when an account stops being an investment, so the kind is
    checked every time.

    Args:
        accounts: The account rows.
        readings: Readings by account id.
        balances: Balances by account id.

    Returns:
        The same rows.
    """
    for account in accounts:
        account.investment_return = (
            build_investment_return(
                readings.get(account.id, []), balances.get(account.id, 0.0)
            )
            if account.kind == AccountKind.INVESTMENT.value
            else None
        )
    return accounts


def active_counts_by_kind(db: Session, user_id: uuid.UUID) -> dict[str, int]:
    """Return how many unarchived accounts the user has of each kind, in one query.

    Args:
        db: Open database session.
        user_id: Owner of the rows.

    Returns:
        Count by kind; a kind with no unarchived account is absent.
    """
    rows = (
        db.query(AccountModel.kind, func.count(AccountModel.id))
        .filter(
            AccountModel.user_id == user_id,
            AccountModel.archived.is_(False),
        )
        .group_by(AccountModel.kind)
        .all()
    )
    return {kind: total for kind, total in rows}


def attach_role_locks(accounts: list[AccountModel], counts: dict[str, int]):
    """Set `role_locked` on each account row that is the last of a protected kind.

    Args:
        accounts: The account rows.
        counts: Unarchived accounts per kind.

    Returns:
        The same rows.
    """
    protected = protected_kind_values()
    for account in accounts:
        account.role_locked = (
            not account.archived
            and account.kind in protected
            and counts.get(account.kind, 0) <= 1
        )
    return accounts


#: Kinds whose balance is money owed. This set exists to *report* the debt line,
#: not to subtract it -- the balances are already negative, and subtracting them
#: a second time is the bug this comment is here to prevent.
DEBT_KINDS = frozenset({AccountKind.DEBT.value})


def net_worth(db: Session, user_id: uuid.UUID) -> NetWorth | None:
    """Return the user's net worth, debt and recorded investment gain.

    Sums the balances of counted, unarchived accounts (a debt's is already
    negative) plus the latest reading on each counted investment account. Debt is
    reported again as a positive magnitude, not subtracted twice.

    Args:
        db: Open database session.
        user_id: Whose accounts.

    Returns:
        The three figures; None when the user does not exist.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None

    accounts = (
        db.query(AccountModel)
        .filter(
            AccountModel.user_id == user_id,
            AccountModel.archived.is_(False),
        )
        .all()
    )
    balances = balances_by_account(db, user_id)

    counted = sum(
        balances.get(account.id, 0.0)
        for account in accounts
        if account.counts_toward_net_worth
    )
    owed = sum(
        balances.get(account.id, 0.0)
        for account in accounts
        if account.kind in DEBT_KINDS and account.counts_toward_net_worth
    )

    # What the holdings are worth, over what was paid for them. Added because the
    # ledger only knows what went in, so a portfolio that had doubled left the
    # headline unmoved. The *latest* reading per account and never a sum of them:
    # these are levels, so adding a column of them inflates the figure further
    # with every month recorded. See Finances/utils/returns.py.
    #
    # Gated on both kind and the count-toward flag, so an account deliberately
    # excluded from the total cannot smuggle its gain into it.
    readings = readings_by_account(db, user_id)
    gain = 0.0
    for account in accounts:
        if not account.counts_toward_net_worth:
            continue
        if account.kind != AccountKind.INVESTMENT.value:
            continue
        found = latest_reading(
            [(month, difference) for month, difference, _ in readings.get(account.id, [])]
        )
        if found is not None:
            gain += found[1]
    gain = round(gain, 2)

    return NetWorth(
        net_worth=round(counted + gain, 2),
        debt_total=round(abs(owed), 2),
        investment_gain=gain,
    )


def get_accounts(db: Session, user_id: uuid.UUID, include_archived: bool = False):
    """Return the user's accounts with balances, role locks and investment returns.

    A user with no accounts at all gets the default ones seeded (and committed)
    first.

    Args:
        db: Open database session.
        user_id: Whose accounts.
        include_archived: Also return archived accounts.

    Returns:
        The account rows by position, then name; None when the user does not
        exist.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None

    accounts = db.query(AccountModel).filter(AccountModel.user_id == user_id).all()
    if not accounts:
        accounts = seed_default_accounts(db, user_id)

    if not include_archived:
        accounts = [account for account in accounts if not account.archived]

    accounts.sort(key=lambda account: (account.position, account.name))
    attach_role_locks(accounts, active_counts_by_kind(db, user_id))
    balances = balances_by_account(db, user_id)
    attach_investment_returns(accounts, readings_by_account(db, user_id), balances)
    return attach_balances(accounts, balances)


def get_account(db: Session, user_id: uuid.UUID, account_id: uuid.UUID):
    """Return one of the user's accounts with its balance, return and role lock.

    Args:
        db: Open database session.
        user_id: Whose account.
        account_id: The account.

    Returns:
        The account row; None when it is not the user's.
    """
    account = (
        db.query(AccountModel)
        .filter(AccountModel.id == account_id, AccountModel.user_id == user_id)
        .first()
    )
    if account is None:
        return None

    account.balance = balance_of(db, user_id, account_id)
    attach_investment_returns(
        [account], {account.id: readings_for_account(db, user_id, account_id)},
        {account.id: account.balance},
    )
    attach_role_locks([account], active_counts_by_kind(db, user_id))
    return account


def create_account(db: Session, user_id: uuid.UUID, data: AccountCreate):
    """Create an account for the user.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose account.
        data: The account.

    Returns:
        The new account row, balance 0; None when the user does not exist.

    Raises:
        ValueError: If the user already has an account of that name, ignoring
            case.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None

    existing = (
        db.query(AccountModel)
        .filter(AccountModel.user_id == user_id, AccountModel.name.ilike(data.name))
        .first()
    )
    if existing:
        raise ValueError("An account with that name already exists")

    account = AccountModel(
        id=uuid.uuid4(),
        user_id=user_id,
        name=data.name,
        kind=data.kind.value,
        income_share=data.income_share,
        archived=data.archived,
        position=data.position,
        counts_toward_net_worth=data.counts_toward_net_worth,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    account.balance = 0.0
    account.investment_return = None
    attach_role_locks([account], active_counts_by_kind(db, user_id))
    return account


def update_account(db: Session, user_id: uuid.UUID, account_id: uuid.UUID, data: AccountUpdate):
    """Change the fields sent on one of the user's accounts.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose account.
        account_id: The account.
        data: The fields to change.

    Returns:
        The updated account row with balance, return and role lock; None when it
        is not the user's.

    Raises:
        ValueError: If archiving it or changing its kind would leave no unarchived
            spending or savings account, or another account has the new name.
    """
    account = (
        db.query(AccountModel)
        .filter(AccountModel.id == account_id, AccountModel.user_id == user_id)
        .first()
    )
    if account is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    if "kind" in update_data and update_data["kind"] is not None:
        kind = update_data["kind"]
        update_data["kind"] = kind.value if hasattr(kind, "value") else kind

    # Two of the three ways to take an account out of service land here, and
    # the kind change is the one that looks harmless: re-kinding the only
    # spending account to "other" empties the role just as thoroughly as
    # deleting it, and nothing on screen would say so.
    new_kind = update_data.get("kind")
    leaving_role = new_kind is not None and new_kind != account.kind
    being_archived = update_data.get("archived") is True and not account.archived
    if (leaving_role or being_archived) and would_orphan_role(db, user_id, account):
        raise ValueError(
            role_refusal(account, "archiving" if being_archived else "changing the kind of")
        )

    new_name = update_data.get("name")
    if new_name is not None:
        clash = (
            db.query(AccountModel)
            .filter(
                AccountModel.user_id == user_id,
                AccountModel.id != account_id,
                AccountModel.name.ilike(new_name),
            )
            .first()
        )
        if clash:
            raise ValueError("An account with that name already exists")

    for key, value in update_data.items():
        setattr(account, key, value)

    db.commit()
    db.refresh(account)
    account.balance = balance_of(db, user_id, account_id)
    # Recomputed rather than carried over: this request may have just changed the
    # kind, and an account that has stopped being an investment must stop
    # reporting a return in the very response that changed it.
    attach_investment_returns(
        [account], {account.id: readings_for_account(db, user_id, account_id)},
        {account.id: account.balance},
    )
    attach_role_locks([account], active_counts_by_kind(db, user_id))
    return account


def delete_account(db: Session, user_id: uuid.UUID, account_id: uuid.UUID):
    """Delete one of the user's accounts, refusing while anything depends on it.

    Refused when it is the last of a protected kind, holds any transactions
    (archive it instead), or is used by a standing instruction or sinking fund.
    Otherwise its targets, emptied import records, category limits and readings go
    with it. Commits.

    Args:
        db: Open database session.
        user_id: Whose account.
        account_id: The account.

    Returns:
        The deleted account row; None when it is not the user's.

    Raises:
        ValueError: If any refusal above applies; the message names what to fix.
    """
    account = (
        db.query(AccountModel)
        .filter(AccountModel.id == account_id, AccountModel.user_id == user_id)
        .first()
    )
    if account is None:
        return None

    # First, because it is the only refusal here that clearing something else
    # cannot lift. Telling someone to repoint three standing instructions and
    # then refusing anyway would be the wrong order to find that out in.
    if would_orphan_role(db, user_id, account):
        raise ValueError(role_refusal(account, "deleting"))

    count = (
        db.query(func.count(TransactionModel.id))
        .filter(TransactionModel.account_id == account_id)
        .scalar()
    )
    if count:
        raise ValueError(
            f"{account.name} has {count} transactions. Archive it instead of deleting."
        )

    rules = (
        db.query(RecurringTransactionModel)
        .filter(
            RecurringTransactionModel.user_id == user_id,
            (RecurringTransactionModel.account_id == account_id)
            | (RecurringTransactionModel.to_account_id == account_id),
        )
        .all()
    )
    if rules:
        named = ", ".join(rule.description or rule.kind for rule in rules[:3])
        raise ValueError(
            f"{account.name} is still used by {len(rules)} standing "
            f"instruction{'s' if len(rules) != 1 else ''} ({named}). "
            "Stop or repoint them first."
        )

    funds = (
        db.query(SinkingFundModel)
        .filter(
            SinkingFundModel.user_id == user_id,
            (SinkingFundModel.from_account_id == account_id)
            | (SinkingFundModel.to_account_id == account_id),
        )
        .all()
    )
    if funds:
        named = ", ".join(fund.name for fund in funds[:3])
        raise ValueError(
            f"{account.name} is still used by {len(funds)} sinking "
            f"fund{'s' if len(funds) != 1 else ''} ({named}). "
            "Remove or repoint them first."
        )

    db.query(BudgetTargetModel).filter(
        BudgetTargetModel.user_id == user_id,
        BudgetTargetModel.account_id == account_id,
    ).delete(synchronize_session=False)

    # Import records with nothing left in them: the transaction count above is
    # zero, so every row an import wrote here is already gone, and the record
    # would otherwise hold the account in place.
    db.query(ImportModel).filter(
        ImportModel.user_id == user_id,
        ImportModel.account_id == account_id,
    ).delete(synchronize_session=False)

    # The account's category limits go with it. They are a foreign key, so
    # leaving them is not untidiness -- it is an integrity error on the delete.
    db.query(AccountCategoryLimitModel).filter(
        AccountCategoryLimitModel.user_id == user_id,
        AccountCategoryLimitModel.account_id == account_id,
    ).delete(synchronize_session=False)

    db.query(AccountCategoryMonthLimitModel).filter(
        AccountCategoryMonthLimitModel.user_id == user_id,
        AccountCategoryMonthLimitModel.account_id == account_id,
    ).delete(synchronize_session=False)

    # The recorded investment readings go too -- same reason as the limits above:
    # a foreign key, so leaving them is an integrity error on the delete rather
    # than untidiness. Written out literally for this one model, like its
    # neighbours: a loop over models with a computed filter once compiled to an
    # unfiltered DELETE and emptied a table.
    db.query(AccountMonthValueModel).filter(
        AccountMonthValueModel.user_id == user_id,
        AccountMonthValueModel.account_id == account_id,
    ).delete(synchronize_session=False)

    db.delete(account)
    db.commit()
    return account


# ------------------------------------------- recording what a holding is worth --

def set_month_value(
    db: Session,
    user_id: uuid.UUID,
    account_id: uuid.UUID,
    data: AccountMonthValueUpsert,
):
    """Record or replace one month's reading for an investment account.

    A market value is turned into the stored level by subtracting the ledger as it
    stood at the month's end (or today, for the current month). Commits.

    Args:
        db: Open database session.
        user_id: Whose account.
        account_id: The account.
        data: The month and either a market value or a difference.

    Returns:
        The account row with its updated return; None when it is not the user's.

    Raises:
        ValueError: If the account is not an investment account.
    """
    account = (
        db.query(AccountModel)
        .filter(AccountModel.id == account_id, AccountModel.user_id == user_id)
        .first()
    )
    if account is None:
        return None

    if account.kind != AccountKind.INVESTMENT.value:
        raise ValueError(
            f"{account.name} is not an investment account, so it has no market "
            "value to record."
        )

    month = data.month.replace(day=1)

    if data.difference_amount is not None:
        difference = round(data.difference_amount, 2)
        market = None
    else:
        ledger = ledger_balance_as_of(
            db, user_id, account_id, measured_on(month, user_today(db, user_id))
        )
        difference = round(data.market_value - ledger, 2)
        market = round(data.market_value, 2)

    existing = (
        db.query(AccountMonthValueModel)
        .filter(
            AccountMonthValueModel.user_id == user_id,
            AccountMonthValueModel.account_id == account_id,
            AccountMonthValueModel.month == month,
        )
        .first()
    )

    if existing is None:
        db.add(
            AccountMonthValueModel(
                id=uuid.uuid4(),
                user_id=user_id,
                account_id=account_id,
                month=month,
                difference_amount=difference,
                market_value=market,
            )
        )
    else:
        existing.difference_amount = difference
        existing.market_value = market

    db.commit()
    return get_account(db, user_id, account_id)


def clear_month_value(
    db: Session, user_id: uuid.UUID, account_id: uuid.UUID, month
):
    """Delete one month's reading; clearing a month with none is not an error.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose account.
        account_id: The account.
        month: Any day of the month.

    Returns:
        The account row; None when it is not the user's.
    """
    db.query(AccountMonthValueModel).filter(
        AccountMonthValueModel.user_id == user_id,
        AccountMonthValueModel.account_id == account_id,
        AccountMonthValueModel.month == month.replace(day=1),
    ).delete(synchronize_session=False)
    db.commit()
    return get_account(db, user_id, account_id)
