import uuid
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app._database.models import (
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


def seed_default_accounts(db: Session, user_id: uuid.UUID) -> list[AccountModel]:
    """Give a new account holder the starting pots from the project notes.

    A starting point, not a complete set: anything more particular than these
    is theirs to create, so the list stays short rather than guessing at pots
    they would only have to delete.

    Done lazily on first read rather than at signup, so accounts that already
    existed before this module get them too.
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
    return {kind.value for kind in PROTECTED_KINDS}


def would_orphan_role(
    db: Session, user_id: uuid.UUID, account: AccountModel
) -> bool:
    """True when taking this account out of service would leave its role empty.

    "Out of service" is deletion, archiving, or changing the kind away -- all
    three end with the student having no account of that kind, and the last of
    those is the one that looks harmless.

    Reads **non-archived** accounts only. An archived spending account is not
    offered anywhere and is not what safe-to-spend reads, so it cannot stand in
    for the one being removed. By the same rule an account that is *already*
    archived can be deleted freely: it left service when it was archived, and
    removing it now changes nothing.
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
    reason = PROTECTED_REASON.get(account.kind, "the app depends on it")
    return (
        f"{account.name} is your only {account.kind} account and {reason}. "
        f"Create another {account.kind} account before {verb} this one."
    )


def balances_by_account(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, float]:
    """Every account's balance in one grouped query, not one query per account."""
    rows = (
        db.query(TransactionModel.account_id, func.sum(TransactionModel.amount))
        .filter(TransactionModel.user_id == user_id)
        .group_by(TransactionModel.account_id)
        .all()
    )
    return {account_id: round(total or 0.0, 2) for account_id, total in rows}


def balance_of(db: Session, user_id: uuid.UUID, account_id: uuid.UUID) -> float:
    """One account's balance, summed by the database rather than in Python.

    `balances_by_account` groups the user's whole ledger, which is right when
    every account's figure is wanted and wasteful when one is: answering "what
    is in Chequing" used to read and sum every transaction in every other
    account and then throw all of it away.
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
    """What the ledger said on a given day. `balance_of` with one extra filter.

    Needed because a reading recorded against August must be measured against
    August's balance, not today's. Using the all-time balance for a past month
    would subtract a figure that includes every deposit made since, turning a
    recorded gain into an invented loss.
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


def measured_on(month) -> "date":
    """The day a month's reading is measured against.

    The last day of the month, or today if the month has not finished -- you
    cannot measure August against the 31st on the 14th, and reaching for the end
    of an unfinished month would count deposits that have not happened.
    """
    _, month_end = month_bounds(month)
    return min(month_end, date.today())


def readings_by_account(
    db: Session, user_id: uuid.UUID
) -> dict[uuid.UUID, list[StoredReading]]:
    """Every reading the user has recorded, grouped by account in one query.

    One query rather than one per account: the account list shows a figure on
    every card, and asking per row is the N+1 the performance pass removed from
    the dashboard. A year of monthly readings on a handful of accounts is a few
    dozen rows, so grouping in Python costs nothing.
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
    """One account's readings, when the whole ledger of them is not wanted."""
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
    """The reading that applies, as the client receives it. None if there is none.

    `for_month` is what carries a figure forward: the month's own reading, or the
    last one taken before it. Omitted -- which is what the account card does --
    it means the latest reading overall, since a card is not scoped to a month.

    The percentage is computed here and not in the client, following the rule
    recorded on `ProgressBar`: the server rounds and the client renders, or two
    opinions on the same division disagree at the boundary.
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
    """Graft each investment account's figure on, the way `attach_balances` does.

    **Gated on kind, every time.** Rows are deliberately left behind when an
    account stops being an investment, so the kind check is what stops a Savings
    account that used to be an Investments account reporting a return.
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
    """How many non-archived accounts the user holds of each kind, in one query.

    Grouped rather than counted per account: the flag below is wanted for every
    row of the list, and asking once per row is the N+1 the performance pass
    spent a day removing from the dashboard.
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
    """Flag the accounts the app will refuse to let go of.

    Derived and attached here rather than worked out in the client, for the
    same reason every other figure is: the rule that decides it lives in
    `would_orphan_role`, and a second copy in React would be free to disagree.

    It says "this is the last of a role", not "this can be deleted" -- history
    and standing instructions refuse deletion too, for their own reasons.
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
    """What you have less what you owe, and the debt on its own.

    Computed here rather than in the client because two screens show it -- the
    budget page and the dashboard -- and a rule about which accounts count is
    exactly the kind that drifts when it is written twice. The dashboard's old
    figure was a plain client-side sum, which counted a debt account as savings.

    Archived accounts are excluded, matching what `get_accounts` already
    returns, so the headline moves with the list rather than disagreeing with it.
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
    """Refuses while anything still points at the account.

    Deleting would cascade its transactions away, silently changing balances
    elsewhere if any were transfer halves. Archiving is the safe route.

    Standing instructions and sinking funds are refused rather than removed,
    because each is a decision the student made and neither is history that
    tidying an account should quietly revoke: a rent instruction deleted as a
    side effect stops paying rent. They are named in the message so it is
    obvious what to repoint or stop first.

    Budget targets are the exception and go with the account. A target is a
    planning number scoped to one account and one month -- it has no meaning
    once the account is gone, and nothing reads it as history.
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
    """Record, or replace, one month's reading for an investment account.

    The client sends `market_value` -- the number you can read straight off a
    statement -- and the **level is what gets stored**, derived by subtracting
    what the ledger said at the end of that month. Storing the level rather than
    the market value is what makes the figure survive a later deposit: a deposit
    raises plain value and market value together, so the level does not move,
    where a stored market value would be measured against a bigger ledger and
    report the gain as a loss.

    An upsert rather than an insert, so correcting a month you fat-fingered is
    the same gesture as recording it. The unique index would refuse a second row
    anyway; this is what makes refusing unnecessary.

    Refuses a non-investment account outright. Every read path gates on kind, so
    storing a reading against a Savings account would be a write that silently
    does nothing -- the worst kind of accepted request.
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
        ledger = ledger_balance_as_of(db, user_id, account_id, measured_on(month))
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
    """Forget one month's reading.

    Returns the account either way: clearing a month that holds no reading is
    already the state being asked for, so it is not an error.

    The filter is written out for the one model against the three literal
    columns. Nothing here is computed, and that is deliberate -- a delete whose
    conditions are assembled rather than written cannot be checked by reading it.
    """
    db.query(AccountMonthValueModel).filter(
        AccountMonthValueModel.user_id == user_id,
        AccountMonthValueModel.account_id == account_id,
        AccountMonthValueModel.month == month.replace(day=1),
    ).delete(synchronize_session=False)
    db.commit()
    return get_account(db, user_id, account_id)
