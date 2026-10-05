from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app._database.dependencies import DBSession
from app.shared.dates import user_today
from app.Auth.services.access import VerifiedUserId
from app.Finances.schemas.account import (
    Account,
    AccountActivity,
    AccountCreate,
    AccountMonthValueUpsert,
    AccountUpdate,
    NetWorth,
)
from app.Finances.schemas.safe import SafeToSpend
from app.Finances.schemas.subscription import SubscriptionCandidate, SubscriptionConfirm
from app.Finances.schemas.recurring import RecurringTransaction
from app.Finances.schemas.sinking import (
    ContributionRequest,
    SinkingFund,
    SinkingFundCreate,
    SinkingFundUpdate,
)
from app.Finances.services.sinking_service import (
    contribute,
    create_fund,
    delete_fund,
    list_funds,
    undo_contribution,
    update_fund,
)
from app.Finances.services.safe_service import safe_to_spend
from app.Finances.services.forecast_service import forecast
from app.Finances.schemas.forecast import CashFlowForecast
from app.Finances.services.plan_service import plan
from app.Finances.schemas.plan import AnnualPlan
from app.Finances.services.subscription_service import confirm_subscription, find_subscriptions
from app.Finances.schemas.budget import (
    BudgetSummary,
    TermBudget,
    AccountCategoryLimitUpsert,
    BudgetTargetUpsert,
    SpendCategory,
    SpendCategoryCreate,
    SpendCategoryUpdate,
)
from app.Finances.schemas.deposit import DepositCreate, DepositPreview
from app.Finances.schemas.tuition import (
    CourseCost,
    TuitionCreate,
    TuitionPayment,
    TuitionPreview,
    TuitionUpdate,
)
from app.Finances.schemas.transaction import (
    Transaction,
    TransactionCreate,
    TransactionUpdate,
    TransferCreate,
)
from app.Finances.services.account_service import (
    clear_month_value,
    create_account,
    delete_account,
    get_account,
    get_accounts,
    net_worth,
    set_month_value,
    update_account,
)
from app.Finances.services.tuition_service import (
    billable_courses,
    course_cost,
    delete_tuition,
    get_tuition,
    preview_tuition,
    record_tuition,
    term_budget,
    update_tuition,
)
from app.Finances.services.transaction_service import (
    create_transaction,
    create_transfer,
    delete_transaction,
    get_transaction,
    list_transactions,
    update_transaction,
)
from app.Finances.services.budget_service import (
    create_category,
    delete_category,
    get_budget_summary,
    get_categories,
    set_account_category_limit,
    set_target,
    update_category,
)
from app.Finances.services.activity_service import get_account_activity
from app.Finances.services.deposit_service import preview_deposit, record_deposit
from app.shared.errors import error_user, responses
from app.shared import audit
from app.Usage.services.usage_service import CREATE, record as record_usage

router = APIRouter()

ACCOUNT_404 = {404: {"description": "Account not found"}}
TRANSACTION_404 = {404: {"description": "Transaction not found"}}


# ----------------------------------------------------------------- accounts --

FUND_404 = {404: {"description": "Sinking fund not found"}}
FUND_BOTH = {**FUND_404, 400: {"description": "Invalid fund"}}


@router.get(
    "/{user_id}/sinking-funds",
    response_model=list[SinkingFund],
    responses=responses["user_404"],
)
def get_sinking_funds(
    user_id: VerifiedUserId,
    db: DBSession,
    include_archived: bool = Query(default=False, description="Also return archived funds"),
):
    """Every fund, soonest due first, with this month's figure derived."""
    funds = list_funds(db, user_id, include_archived)
    if funds is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return funds


@router.post(
    "/{user_id}/sinking-funds",
    response_model=SinkingFund,
    responses=responses["user_both"],
)
def add_sinking_fund(user_id: VerifiedUserId, fund: SinkingFundCreate, db: DBSession):
    try:
        created = create_fund(db, user_id, fund)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return created


@router.patch(
    "/{user_id}/sinking-funds/{fund_id}",
    response_model=SinkingFund,
    responses=FUND_BOTH,
)
def edit_sinking_fund(
    user_id: VerifiedUserId, fund_id: UUID, fund: SinkingFundUpdate, db: DBSession
):
    """Change a fund. The monthly figure follows on the next read, not here."""
    try:
        updated = update_fund(db, user_id, fund_id, fund)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="Sinking fund not found")

    return updated


@router.post(
    "/{user_id}/sinking-funds/{fund_id}/contribute",
    response_model=SinkingFund,
    responses=FUND_BOTH,
)
def add_contribution(
    user_id: VerifiedUserId,
    fund_id: UUID,
    contribution: ContributionRequest,
    db: DBSession,
):
    """Set this month's money aside for real, writing the transfer."""
    try:
        funded = contribute(db, user_id, fund_id, contribution)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if funded is None:
        raise HTTPException(status_code=404, detail="Sinking fund not found")

    return funded


@router.delete(
    "/{user_id}/sinking-funds/{fund_id}/contributions/{contribution_id}",
    response_model=SinkingFund,
    responses=FUND_404,
)
def remove_contribution(
    user_id: VerifiedUserId, fund_id: UUID, contribution_id: UUID, db: DBSession
):
    """Take a month's set-aside back, moving the money with it."""
    undone = undo_contribution(db, user_id, fund_id, contribution_id)
    if undone is None:
        raise HTTPException(status_code=404, detail="Contribution not found")

    return undone


@router.delete(
    "/{user_id}/sinking-funds/{fund_id}",
    response_model=SinkingFund,
    responses=FUND_404,
)
def remove_sinking_fund(user_id: VerifiedUserId, fund_id: UUID, db: DBSession):
    """Remove a fund and every transfer its contributions wrote.

    Archiving is the way to keep the history; this is for one entered by
    mistake.
    """
    deleted = delete_fund(db, user_id, fund_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Sinking fund not found")

    audit.deletion("sinking_fund", user_id=user_id, target_id=fund_id, detail=deleted.name)
    return deleted


@router.get(
    "/{user_id}/forecast",
    response_model=CashFlowForecast,
    responses=responses["user_404"],
)
def get_forecast(user_id: VerifiedUserId, db: DBSession):
    """Where the spending accounts are heading, to the end of the term.

    A daily projection from today's balance, the standing instructions, pay
    from scheduled shifts, and the recent pace of one-off spending -- with the
    first day it goes below zero, runway, the places one-off spending goes
    most, and every assumption it rests on.
    """
    result = forecast(db, user_id)
    if result is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return result


@router.get(
    "/{user_id}/plan",
    response_model=AnnualPlan,
    responses=responses["user_both"],
)
def get_plan(
    user_id: VerifiedUserId,
    db: DBSession,
    target: float | None = Query(None, ge=0, le=10_000_000, description="Balance to reach"),
    until: date | None = Query(None, description="When to reach it; defaults to the school year's end"),
):
    """The year as one running balance, month by month -- and, given a target,
    the extra weekly hours it would take."""
    try:
        result = plan(db, user_id, target=target, target_on=until)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return result


@router.get(
    "/{user_id}/safe-to-spend",
    response_model=SafeToSpend,
    responses=responses["user_404"],
)
def get_safe_to_spend(user_id: VerifiedUserId, db: DBSession):
    """What can be spent between now and the next time money arrives.

    The window ends the day before the next pay date, or at the end of the month
    when no job has a pay rule. Two figures come back: `safe_now` is cash in a
    spending account less what is committed, and `safe_soon` adds confirmed work
    not yet paid for. The first is the answer; the second is context.
    """
    safe = safe_to_spend(db, user_id)
    if safe is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return safe


@router.get(
    "/{user_id}/subscriptions",
    response_model=list[SubscriptionCandidate],
    responses=responses["user_404"],
)
def get_subscriptions(user_id: VerifiedUserId, db: DBSession):
    """Recurring charges nobody told the app about.

    Only an expense with no standing instruction behind it can appear here --
    one that already has a `recurring_id` is already known. A run counts once
    it has repeated three times on a description, an amount within 10% of its
    own median, and a gap that reads as weekly, fortnightly or monthly. Each
    finding comes back with a standing instruction already filled in, ready to
    submit as-is.
    """
    subscriptions = find_subscriptions(db, user_id)
    if subscriptions is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return subscriptions


@router.post(
    "/{user_id}/subscriptions/confirm",
    response_model=RecurringTransaction,
    responses=responses["user_both"],
)
def confirm_subscription_route(user_id: VerifiedUserId, payload: SubscriptionConfirm, db: DBSession):
    """Turn a finding into a standing instruction, and stop re-finding it.

    The charges named in `transaction_ids` are tagged with the new
    instruction's id -- without that, the same history has no `recurring_id`
    and qualifies as a pattern again on the very next read.
    """
    try:
        rule = confirm_subscription(db, user_id, payload.transaction_ids, payload.instruction)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if rule is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return rule


@router.get("/{user_id}/accounts", response_model=list[Account], responses=responses["user_404"])
def list_accounts(user_id: VerifiedUserId, db: DBSession, include_archived: bool = False):
    """The account holder's pots, seeded with the default four on first read."""
    accounts = get_accounts(db, user_id, include_archived)
    if accounts is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return accounts


@router.post("/{user_id}/accounts", response_model=Account, responses=responses["user_both"])
def add_account(user_id: VerifiedUserId, account: AccountCreate, db: DBSession):
    try:
        created = create_account(db, user_id, account)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return created


@router.get("/{user_id}/net-worth", response_model=NetWorth, responses=responses["user_404"])
def read_net_worth(user_id: VerifiedUserId, db: DBSession):
    """What counts, less what is owed -- and the debt on its own line.

    Its own endpoint rather than two floats on the month's budget summary: this
    figure is all-time, and one that appeared to respond to the month picker
    would invite exactly the wrong question about it.
    """
    figure = net_worth(db, user_id)
    if figure is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return figure


@router.get("/{user_id}/accounts/{account_id}", response_model=Account, responses=ACCOUNT_404)
def get_single_account(user_id: VerifiedUserId, account_id: UUID, db: DBSession):
    account = get_account(db, user_id, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    return account


@router.get(
    "/{user_id}/accounts/{account_id}/activity",
    response_model=AccountActivity,
    responses=ACCOUNT_404,
)
def account_activity(
    user_id: VerifiedUserId,
    account_id: UUID,
    db: DBSession,
    month: date | None = None,
):
    """One account's month: daily flow, totals, categories and its target.

    Served whole rather than assembled in the browser so the rule for what
    counts as money leaving an account is stated once, here and in the budget
    summary, and cannot drift between the two pages.
    """
    activity = get_account_activity(
        db, user_id, account_id, month or user_today(db, user_id)
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="Account not found")

    return activity


@router.put(
    "/{user_id}/accounts/{account_id}/month-value",
    response_model=Account,
    responses=ACCOUNT_404,
)
def record_month_value(
    user_id: VerifiedUserId,
    account_id: UUID,
    reading: AccountMonthValueUpsert,
    db: DBSession,
):
    """Record what an investment account's holding is worth, for one month.

    Send `market_value` -- the figure off a statement -- and the service stores
    how far that sits above or below the month's ledger balance. `difference_amount`
    is accepted instead, for setting the figure without a ledger lookup.

    An upsert: sending the same month twice corrects it rather than failing, which
    is also what the unique index would otherwise have to refuse.

    Returns the whole account, so the card's figure comes back in this response
    rather than needing a second fetch to see what changed.
    """
    try:
        updated = set_month_value(db, user_id, account_id, reading)
    except ValueError as exc:
        # Not an investment account, so there is nothing for a reading to mean.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="Account not found")

    return updated


@router.delete(
    "/{user_id}/accounts/{account_id}/month-value",
    response_model=Account,
    responses=ACCOUNT_404,
)
def remove_month_value(
    user_id: VerifiedUserId,
    account_id: UUID,
    db: DBSession,
    month: date,
):
    """Forget one month's reading.

    `month` is required rather than defaulted to today: a default here would mean
    a request that forgot the parameter silently deleted the current month's
    figure, which is the one most likely to be the one you just typed.
    """
    updated = clear_month_value(db, user_id, account_id, month)
    if updated is None:
        raise HTTPException(status_code=404, detail="Account not found")

    audit.deletion(
        "investment reading",
        user_id=user_id,
        target_id=account_id,
        detail=f"{updated.name} {month:%Y-%m}",
    )
    return updated


@router.patch("/{user_id}/accounts/{account_id}", response_model=Account, responses=ACCOUNT_404)
def edit_account(user_id: VerifiedUserId, account_id: UUID, account: AccountUpdate, db: DBSession):
    try:
        updated = update_account(db, user_id, account_id, account)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="Account not found")

    return updated


@router.delete("/{user_id}/accounts/{account_id}", response_model=Account, responses=ACCOUNT_404)
def remove_account(user_id: VerifiedUserId, account_id: UUID, db: DBSession):
    try:
        removed = delete_account(db, user_id, account_id)
    except ValueError as exc:
        # Refused because it still holds history; archiving is the safe route.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if removed is None:
        raise HTTPException(status_code=404, detail="Account not found")

    audit.deletion("account", user_id=user_id, target_id=account_id, detail=removed.name)
    return removed


# ------------------------------------------------------------- transactions --

@router.get("/{user_id}/transactions", response_model=list[Transaction], responses=responses["user_404"])
def list_user_transactions(
    user_id: VerifiedUserId,
    db: DBSession,
    account_id: UUID | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    """Movements, newest first. `start`/`end` bound `occurred_on` inclusively.

    An impossible window is a 400 and an unknown account a 404, rather than the
    empty list both used to return -- on a money page "you have nothing" is a
    worse answer than an error, because it looks like a fact.
    """
    try:
        return list_transactions(db, user_id, account_id, limit, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{user_id}/transactions", response_model=Transaction, responses=ACCOUNT_404)
def add_transaction(user_id: VerifiedUserId, transaction: TransactionCreate, db: DBSession):
    try:
        created = create_transaction(db, user_id, transaction)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail="Account not found")

    record_usage(db, user_id, CREATE, "budget")
    return created


@router.post("/{user_id}/transfers", response_model=list[Transaction], responses=ACCOUNT_404)
def add_transfer(user_id: VerifiedUserId, transfer: TransferCreate, db: DBSession):
    """Moves money between two accounts as a single committed pair."""
    try:
        created = create_transfer(db, user_id, transfer)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail="Account not found")

    record_usage(db, user_id, CREATE, "budget")
    return created


@router.get("/{user_id}/transactions/{transaction_id}", response_model=Transaction, responses=TRANSACTION_404)
def get_single_transaction(user_id: VerifiedUserId, transaction_id: UUID, db: DBSession):
    transaction = get_transaction(db, user_id, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return transaction


@router.patch("/{user_id}/transactions/{transaction_id}", response_model=Transaction, responses=TRANSACTION_404)
def edit_transaction(
    user_id: VerifiedUserId, transaction_id: UUID, transaction: TransactionUpdate, db: DBSession
):
    # The service refuses a course or category that is not the caller's, and an
    # amount edit on a tuition row, by raising. Uncaught, both were a 500 -- the
    # tuition one in front of a real user, with a message written for them.
    try:
        updated = update_transaction(db, user_id, transaction_id, transaction)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return updated


@router.delete("/{user_id}/transactions/{transaction_id}", response_model=Transaction, responses=TRANSACTION_404)
def remove_transaction(
    user_id: VerifiedUserId,
    transaction_id: UUID,
    db: DBSession,
    scope: Literal["row", "group"] = "group",
):
    """Remove a movement. `scope` decides how much of a grouped one goes.

    Ignored for a transfer, which is always removed whole.
    """
    removed = delete_transaction(db, user_id, transaction_id, scope)
    if removed is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    audit.deletion(
        "transaction", user_id=user_id, target_id=transaction_id,
        detail=f"scope={scope} amount={removed.amount}",
    )
    return removed


# --------------------------------------------------------------- categories --

CATEGORY_404 = {404: {"description": "Category not found"}}


@router.get("/{user_id}/categories", response_model=list[SpendCategory], responses=responses["user_404"])
def list_categories(user_id: VerifiedUserId, db: DBSession, include_archived: bool = False):
    categories = get_categories(db, user_id, include_archived)
    if categories is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return categories


@router.post("/{user_id}/categories", response_model=SpendCategory, responses=responses["user_both"])
def add_category(user_id: VerifiedUserId, category: SpendCategoryCreate, db: DBSession):
    try:
        created = create_category(db, user_id, category)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return created


@router.patch("/{user_id}/categories/{category_id}", response_model=SpendCategory, responses=CATEGORY_404)
def edit_category(user_id: VerifiedUserId, category_id: UUID, category: SpendCategoryUpdate, db: DBSession):
    updated = update_category(db, user_id, category_id, category)
    if updated is None:
        raise HTTPException(status_code=404, detail="Category not found")

    return updated


@router.delete("/{user_id}/categories/{category_id}", response_model=SpendCategory, responses=CATEGORY_404)
def remove_category(user_id: VerifiedUserId, category_id: UUID, db: DBSession):
    """Removes the label; the expenses it was on are kept and uncategorised."""
    removed = delete_category(db, user_id, category_id)
    if removed is None:
        raise HTTPException(status_code=404, detail="Category not found")

    audit.deletion("category", user_id=user_id, target_id=category_id, detail=removed.name)
    return removed


# ---------------------------------------------------------- planned vs actual --

@router.put("/{user_id}/budget-targets", responses=ACCOUNT_404)
def upsert_budget_target(user_id: VerifiedUserId, target: BudgetTargetUpsert, db: DBSession):
    """Set what one account may spend in one month."""
    saved = set_target(db, user_id, target)
    if saved is None:
        raise HTTPException(status_code=404, detail="Account not found")

    return {
        "account_id": saved.account_id,
        "month": saved.month,
        "planned_amount": saved.planned_amount,
    }


@router.put("/{user_id}/account-category-limits", responses=ACCOUNT_404)
def upsert_account_category_limit(
    user_id: VerifiedUserId, limit: AccountCategoryLimitUpsert, db: DBSession
):
    """Set what one account may spend on one category, or clear it.

    A null `limit_amount` removes the limit. If it was that account's last one,
    the account goes back to the target typed into Planned spend.
    """
    if not set_account_category_limit(db, user_id, limit):
        raise HTTPException(status_code=404, detail="Account or category not found")

    return {
        "account_id": limit.account_id,
        "category_id": limit.category_id,
        "limit_amount": limit.limit_amount,
    }


@router.get("/{user_id}/budget-summary", response_model=BudgetSummary, responses=responses["user_404"])
def budget_summary(user_id: VerifiedUserId, db: DBSession, month: date | None = None):
    """Planned against actual for a month, per account and per category."""
    summary = get_budget_summary(db, user_id, month or user_today(db, user_id))
    if summary is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return summary


# ----------------------------------------------------------------- deposits --

@router.get("/{user_id}/deposit-preview", response_model=DepositPreview, responses=responses["user_404"])
def get_deposit_preview(
    user_id: VerifiedUserId,
    db: DBSession,
    amount: float = Query(..., gt=0),
):
    """How a deposit would divide by the current income shares.

    Served rather than computed client-side so the cent-rounding rule lives in
    one place and the preview always matches what recording actually writes.
    """
    return preview_deposit(db, user_id, amount)


@router.post("/{user_id}/deposits", response_model=list[Transaction], responses=responses["user_both"])
def add_deposit(user_id: VerifiedUserId, deposit: DepositCreate, db: DBSession):
    """Record income and spread it across the accounts in one commit."""
    try:
        created = record_deposit(db, user_id, deposit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail="Account not found")

    record_usage(db, user_id, CREATE, "budget")
    return created


@router.get("/{user_id}/tuition/preview", response_model=TuitionPreview, responses=responses["user_404"])
def preview_tuition_payment(
    user_id: VerifiedUserId,
    db: DBSession,
    cost_per_credit: float = Query(0.0, ge=0),
    fees: float = Query(0.0, ge=0),
    deductions_total: float = Query(0.0, ge=0),
):
    """The arithmetic before anything is written, so the form can show the total."""
    return preview_tuition(db, user_id, cost_per_credit, fees, deductions_total)


@router.post("/{user_id}/tuition", response_model=TuitionPayment, status_code=201, responses=responses["user_400"])
def create_tuition_payment(user_id: VerifiedUserId, data: TuitionCreate, db: DBSession):
    """One ledger row for what left the account, plus what it was made of."""
    try:
        return record_tuition(db, user_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{user_id}/courses/{course_id}/cost", response_model=CourseCost, responses=responses["course_both"])
def get_course_cost(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    """What a course cost: its gross share of tuition, plus what was bought for it."""
    cost = course_cost(db, user_id, course_id)
    if cost is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return cost


@router.get("/{user_id}/tuition/{payment_id}", response_model=TuitionPayment, responses=responses["user_404"])
def read_tuition_payment(user_id: VerifiedUserId, payment_id: UUID, db: DBSession):
    payment = get_tuition(db, user_id, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Tuition payment not found")
    return payment


@router.patch("/{user_id}/tuition/{payment_id}", response_model=TuitionPayment, responses=responses["user_400"])
def edit_tuition_payment(
    user_id: VerifiedUserId, payment_id: UUID, data: TuitionUpdate, db: DBSession
):
    """Correct a payment, moving its ledger row to match."""
    try:
        payment = update_tuition(db, user_id, payment_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payment is None:
        raise HTTPException(status_code=404, detail="Tuition payment not found")
    return payment


@router.delete("/{user_id}/tuition/{payment_id}", status_code=204, responses=responses["user_404"])
def remove_tuition_payment(user_id: VerifiedUserId, payment_id: UUID, db: DBSession):
    """Remove a payment and the ledger row it owns."""
    if delete_tuition(db, user_id, payment_id) is None:
        raise HTTPException(status_code=404, detail="Tuition payment not found")
    return None


@router.get("/{user_id}/term-budget", response_model=TermBudget, responses=responses["user_404"])
def get_term_budget(user_id: VerifiedUserId, db: DBSession):
    """What the current term has cost, measured over the term's own dates."""
    return term_budget(db, user_id)
