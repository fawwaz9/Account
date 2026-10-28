"""Finance routes under /api/finances: accounts, ledger, budgets, funds and forecasts.

Each handler parses the request, calls one Finances service and maps its result
to a status: a service ValueError is a 400 and a None a 404, except where a
handler says otherwise. Standing instructions have their own router
(`recurring.py`) under the same prefix.
"""

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
from app.Finances.schemas.plan import AnnualPlan, PlanReview, SavedPlan
from app.Finances.services.plan_review_service import review as plan_review, save_plan
from app.Finances.services import import_service
from app.Finances.schemas.importing import CommitRequest, ImportPreview, ImportSummary, PreviewRequest
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
    """List the caller's sinking funds, soonest due first, with this month's figure.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        include_archived: Also return archived funds.

    Returns:
        The funds, each with what to set aside this month.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
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
    """Create a sinking fund: a target, a due date and the accounts money moves between.

    Args:
        user_id: The verified caller's id.
        fund: The fund.
        db: Request-scoped database session.

    Returns:
        The created fund.

    Raises:
        HTTPException: 400 if the accounts are the same or not both the caller's;
            404 if the user does not exist.
    """
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
    """Change one of the caller's funds; the monthly figure follows on the next read.

    Args:
        user_id: The verified caller's id.
        fund_id: The fund.
        fund: The fields to change.
        db: Request-scoped database session.

    Returns:
        The updated fund.

    Raises:
        HTTPException: 400 if the accounts would be the same or not both the
            caller's; 404 if the fund is missing or not the caller's.
    """
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
    """Set a month's money aside for a fund, writing the transfer.

    Args:
        user_id: The verified caller's id.
        fund_id: The fund.
        contribution: The optional amount and date.
        db: Request-scoped database session.

    Returns:
        The fund, with the contribution counted.

    Raises:
        HTTPException: 400 if the month is already funded, the target is reached,
            or nothing is left to set aside; 404 if the fund is missing or not the
            caller's.
    """
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
    """Take back one contribution to a fund, deleting its transfer.

    Args:
        user_id: The verified caller's id.
        fund_id: The fund.
        contribution_id: The contribution.
        db: Request-scoped database session.

    Returns:
        The fund without it.

    Raises:
        HTTPException: 404 if the fund or contribution is missing or not the
            caller's.
    """
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
    """Delete a fund and every transfer its contributions wrote.

    Archiving keeps the history; this is for a fund entered by mistake.

    Args:
        user_id: The verified caller's id.
        fund_id: The fund.
        db: Request-scoped database session.

    Returns:
        A copy of the deleted fund.

    Raises:
        HTTPException: 404 if the fund is missing or not the caller's.
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
    """Get where the caller's spending accounts are heading, to the end of the term.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The daily projection, the first day below zero, runway, run-rates and every
        assumption.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    result = forecast(db, user_id)
    if result is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return result


@router.post(
    "/{user_id}/imports/preview",
    response_model=ImportPreview,
    responses=responses["user_both"],
)
def preview_import(user_id: VerifiedUserId, request: PreviewRequest, db: DBSession):
    """Preview what a bank CSV would add to an account, flagging duplicates.

    Args:
        user_id: The verified caller's id.
        request: The account, the file's text and an optional column mapping.
        db: Request-scoped database session.

    Returns:
        Every line read, with status, suggested categories and totals.

    Raises:
        HTTPException: 400 if the file has no rows or too many; 404 if the account
            is missing or not the caller's.
    """
    try:
        result = import_service.preview(db, user_id, request.account_id, request.csv_text, request.mapping)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return result


@router.post(
    "/{user_id}/imports",
    response_model=ImportSummary,
    status_code=201,
    responses=responses["user_both"],
)
def commit_import(user_id: VerifiedUserId, request: CommitRequest, db: DBSession):
    """Import the chosen lines of a CSV, re-read from the same text and mapping.

    Args:
        user_id: The verified caller's id.
        request: The text, mapping, lines, filename and confirmed categories.
        db: Request-scoped database session.

    Returns:
        The import's summary, with a 201.

    Raises:
        HTTPException: 400 if a line is not in the file or cannot be read, or a
            category is not the caller's; 404 if the account is missing or not
            the caller's.
    """
    try:
        result = import_service.commit(db, user_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Account not found")
    record_usage(db, user_id, CREATE, "budget")
    return result


@router.get("/{user_id}/imports", response_model=list[ImportSummary], responses=responses["user_404"])
def list_imports(user_id: VerifiedUserId, db: DBSession):
    """List the caller's past imports, newest first, with what is left of each.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The imports; empty when there are none.
    """
    return import_service.summaries(db, user_id)


@router.delete("/{user_id}/imports/{import_id}", responses=responses["user_404"])
def undo_import(user_id: VerifiedUserId, import_id: UUID, db: DBSession):
    """Remove every row an import wrote, and the import itself.

    Args:
        user_id: The verified caller's id.
        import_id: The import.
        db: Request-scoped database session.

    Returns:
        `{"removed": <rows deleted>}`.

    Raises:
        HTTPException: 404 if the import is missing or not the caller's.
    """
    removed = import_service.undo(db, user_id, import_id)
    if removed is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return {"removed": removed}


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
    """Get the year plan, and the extra weekly hours a target balance would take.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        target: A balance to reach, 0 to 10,000,000 dollars; omit for no goal.
        until: When to reach it; defaults to the school year's end.

    Returns:
        The plan, month by month, with the goal when one can be priced.

    Raises:
        HTTPException: 400 if `until` is not after today or too far ahead; 404 if
            the user does not exist.
    """
    try:
        result = plan(db, user_id, target=target, target_on=until)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return result


@router.post(
    "/{user_id}/plan/saved",
    response_model=SavedPlan,
    responses=responses["user_404"],
)
def keep_plan(user_id: VerifiedUserId, db: DBSession):
    """Save the year plan as it stands, to compare the coming months with.

    Each save is a new row; an earlier plan is never replaced.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The saved plan's identity.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    saved = save_plan(db, user_id)
    if saved is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return saved


@router.get(
    "/{user_id}/plan/review",
    response_model=PlanReview,
    responses=responses["user_404"],
)
def get_plan_review(user_id: VerifiedUserId, db: DBSession):
    """Get each finished month set against the plan saved before it began.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The latest saved plan and the reviewed months; empty when nothing is
        saved.
    """
    return plan_review(db, user_id)


@router.get(
    "/{user_id}/safe-to-spend",
    response_model=SafeToSpend,
    responses=responses["user_404"],
)
def get_safe_to_spend(user_id: VerifiedUserId, db: DBSession):
    """Get what the caller can spend before money next arrives.

    The window ends the day before the next pay date, or at the month's end when no
    job has one. `safe_now` is the answer; `safe_soon` adds hourly work done but not
    yet paid for.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The figures and the commitments behind them.

    Raises:
        HTTPException: 404 if the user does not exist.
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
    """List repeating charges the caller never declared as standing instructions.

    A run qualifies after three charges on one description, within 10% of their
    median, at a weekly, fortnightly or monthly rhythm. Each comes with a standing
    instruction ready to submit.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The findings, most recently seen first.

    Raises:
        HTTPException: 404 if the user does not exist.
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
    """Turn a subscription finding into a standing instruction and tag its charges.

    Args:
        user_id: The verified caller's id.
        payload: The finding's charge ids and the instruction to create.
        db: Request-scoped database session.

    Returns:
        The created standing instruction.

    Raises:
        HTTPException: 400 if an account or category in the instruction is not the
            caller's; 404 if the user does not exist.
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
    """List the caller's accounts with balances, seeding the defaults on first read.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        include_archived: Also return archived accounts.

    Returns:
        The accounts, in the caller's order.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    accounts = get_accounts(db, user_id, include_archived)
    if accounts is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return accounts


@router.post("/{user_id}/accounts", response_model=Account, responses=responses["user_both"])
def add_account(user_id: VerifiedUserId, account: AccountCreate, db: DBSession):
    """Create an account.

    Args:
        user_id: The verified caller's id.
        account: The account.
        db: Request-scoped database session.

    Returns:
        The created account.

    Raises:
        HTTPException: 400 if the caller already has an account of that name; 404
            if the user does not exist.
    """
    try:
        created = create_account(db, user_id, account)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return created


@router.get("/{user_id}/net-worth", response_model=NetWorth, responses=responses["user_404"])
def read_net_worth(user_id: VerifiedUserId, db: DBSession):
    """Get the caller's all-time net worth, debt and recorded investment gain.

    Its own endpoint, not part of the month's budget, because it does not change
    with the month picker.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The three figures.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    figure = net_worth(db, user_id)
    if figure is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return figure


@router.get("/{user_id}/accounts/{account_id}", response_model=Account, responses=ACCOUNT_404)
def get_single_account(user_id: VerifiedUserId, account_id: UUID, db: DBSession):
    """Get one of the caller's accounts.

    Args:
        user_id: The verified caller's id.
        account_id: The account.
        db: Request-scoped database session.

    Returns:
        The account, with its balance.

    Raises:
        HTTPException: 404 if the account is missing or not the caller's.
    """
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
    """Get one account's month: daily flow, totals, categories and its target.

    Args:
        user_id: The verified caller's id.
        account_id: The account.
        db: Request-scoped database session.
        month: Any day of the month to show; defaults to the caller's today.

    Returns:
        The account's activity for the month.

    Raises:
        HTTPException: 404 if the account is missing or not the caller's.
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
    """Record what an investment account's holding is worth for one month.

    Send `market_value` (from a statement) and the stored figure is how far it sits
    above or below that month's ledger, or send `difference_amount` directly.
    Sending the same month again corrects it.

    Args:
        user_id: The verified caller's id.
        account_id: The account.
        reading: The month and one of the two figures.
        db: Request-scoped database session.

    Returns:
        The whole account, with its updated return.

    Raises:
        HTTPException: 400 if the account is not an investment account; 404 if it
            is missing or not the caller's.
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
    """Forget one month's investment reading.

    `month` is required, so a request that forgot it cannot delete the current
    month's figure.

    Args:
        user_id: The verified caller's id.
        account_id: The account.
        db: Request-scoped database session.
        month: Any day of the month to forget.

    Returns:
        The whole account.

    Raises:
        HTTPException: 404 if the account is missing or not the caller's.
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
    """Change the fields sent on one of the caller's accounts.

    Args:
        user_id: The verified caller's id.
        account_id: The account.
        account: The fields to change.
        db: Request-scoped database session.

    Returns:
        The updated account.

    Raises:
        HTTPException: 400 if it would leave no unarchived spending or savings
            account, or another account has the new name; 404 if the account is
            missing or not the caller's.
    """
    try:
        updated = update_account(db, user_id, account_id, account)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="Account not found")

    return updated


@router.delete("/{user_id}/accounts/{account_id}", response_model=Account, responses=ACCOUNT_404)
def remove_account(user_id: VerifiedUserId, account_id: UUID, db: DBSession):
    """Delete one of the caller's accounts, if nothing depends on it.

    Args:
        user_id: The verified caller's id.
        account_id: The account.
        db: Request-scoped database session.

    Returns:
        The deleted account.

    Raises:
        HTTPException: 400 if it is the last spending or savings account, holds
            transactions (archive it instead), or is used by a standing
            instruction or sinking fund; 404 if it is missing or not the caller's.
    """
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
    """List the caller's ledger rows, newest first.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        account_id: Only this account's rows; omit for all.
        start: Earliest date, inclusive.
        end: Latest date, inclusive.
        limit: Most rows to return, 1-500; the oldest are dropped first.

    Returns:
        The rows, each with its group size and owning tuition payment.

    Raises:
        HTTPException: 400 if `start` is after `end`; 404 if the account is not the
            caller's.
    """
    try:
        return list_transactions(db, user_id, account_id, limit, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{user_id}/transactions", response_model=Transaction, responses=ACCOUNT_404)
def add_transaction(user_id: VerifiedUserId, transaction: TransactionCreate, db: DBSession):
    """Record income or an expense on one of the caller's accounts.

    Args:
        user_id: The verified caller's id.
        transaction: The transaction; its amount is a positive magnitude.
        db: Request-scoped database session.

    Returns:
        The recorded row.

    Raises:
        HTTPException: 400 if the kind is transfer, or the category or course is
            not the caller's; 404 if the account is missing or not the caller's.
    """
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
    """Move money between two of the caller's accounts, as one committed pair of rows.

    Args:
        user_id: The verified caller's id.
        transfer: The amount, date and both accounts.
        db: Request-scoped database session.

    Returns:
        The outgoing and incoming rows.

    Raises:
        HTTPException: 404 if either account is missing or not the caller's.
    """
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
    """Get one of the caller's ledger rows.

    Args:
        user_id: The verified caller's id.
        transaction_id: The row.
        db: Request-scoped database session.

    Returns:
        The row, with its group size.

    Raises:
        HTTPException: 404 if the row is missing or not the caller's.
    """
    transaction = get_transaction(db, user_id, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return transaction


@router.patch("/{user_id}/transactions/{transaction_id}", response_model=Transaction, responses=TRANSACTION_404)
def edit_transaction(
    user_id: VerifiedUserId, transaction_id: UUID, transaction: TransactionUpdate, db: DBSession
):
    """Change the fields sent on one of the caller's ledger rows.

    A transfer's other leg follows.

    Args:
        user_id: The verified caller's id.
        transaction_id: The row.
        transaction: The fields to change.
        db: Request-scoped database session.

    Returns:
        The updated row.

    Raises:
        HTTPException: 400 if the category or course is not the caller's, or the
            amount of a tuition row is edited; 404 if the row is missing or not
            the caller's.
    """
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
    """Delete a ledger row, or the whole group it belongs to.

    A transfer is always removed whole; for a deposit, `scope` decides. Records
    that own the rows (a tuition payment, a paycheque, a contribution) go too.

    Args:
        user_id: The verified caller's id.
        transaction_id: The row.
        db: Request-scoped database session.
        scope: "group" (the default) or "row".

    Returns:
        A copy of the row named.

    Raises:
        HTTPException: 404 if the row is missing or not the caller's.
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
    """List the caller's spending categories, seeding the defaults on first read.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        include_archived: Also return archived categories.

    Returns:
        The categories, in the caller's order.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    categories = get_categories(db, user_id, include_archived)
    if categories is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return categories


@router.post("/{user_id}/categories", response_model=SpendCategory, responses=responses["user_both"])
def add_category(user_id: VerifiedUserId, category: SpendCategoryCreate, db: DBSession):
    """Create a spending category.

    Args:
        user_id: The verified caller's id.
        category: The category.
        db: Request-scoped database session.

    Returns:
        The created category.

    Raises:
        HTTPException: 400 if the caller already has a category of that name,
            ignoring case; 404 if the user does not exist.
    """
    try:
        created = create_category(db, user_id, category)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return created


@router.patch("/{user_id}/categories/{category_id}", response_model=SpendCategory, responses=CATEGORY_404)
def edit_category(user_id: VerifiedUserId, category_id: UUID, category: SpendCategoryUpdate, db: DBSession):
    """Rename, archive or reorder one of the caller's categories.

    The service's refusal of a name already in use is not caught here, so it
    surfaces as a 500.

    Args:
        user_id: The verified caller's id.
        category_id: The category.
        category: The fields to change.
        db: Request-scoped database session.

    Returns:
        The updated category.

    Raises:
        HTTPException: 404 if the category is missing or not the caller's.
    """
    updated = update_category(db, user_id, category_id, category)
    if updated is None:
        raise HTTPException(status_code=404, detail="Category not found")

    return updated


@router.delete("/{user_id}/categories/{category_id}", response_model=SpendCategory, responses=CATEGORY_404)
def remove_category(user_id: VerifiedUserId, category_id: UUID, db: DBSession):
    """Delete a category; the expenses it labelled are kept, uncategorised.

    Args:
        user_id: The verified caller's id.
        category_id: The category.
        db: Request-scoped database session.

    Returns:
        The deleted category.

    Raises:
        HTTPException: 404 if the category is missing or not the caller's.
    """
    removed = delete_category(db, user_id, category_id)
    if removed is None:
        raise HTTPException(status_code=404, detail="Category not found")

    audit.deletion("category", user_id=user_id, target_id=category_id, detail=removed.name)
    return removed


# ---------------------------------------------------------- planned vs actual --

@router.put("/{user_id}/budget-targets", responses=ACCOUNT_404)
def upsert_budget_target(user_id: VerifiedUserId, target: BudgetTargetUpsert, db: DBSession):
    """Set what one of the caller's accounts plans to spend in one month.

    Args:
        user_id: The verified caller's id.
        target: The account, the month and the amount.
        db: Request-scoped database session.

    Returns:
        The account id, the month (its first day) and the planned amount.

    Raises:
        HTTPException: 404 if the account is missing or not the caller's.
    """
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
    """Set or clear what one account may spend on one category.

    A null `limit_amount` removes the limit; when it was the account's last one, the
    account goes back to its hand-set target.

    Args:
        user_id: The verified caller's id.
        limit: The account, category, optional month and amount.
        db: Request-scoped database session.

    Returns:
        The account id, category id and limit as sent.

    Raises:
        HTTPException: 404 if the account or category is missing or not the
            caller's.
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
    """Get a month's planned against actual spending, per account and per category.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        month: Any day of the month; defaults to the caller's today.

    Returns:
        The month's budget summary.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
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
    """Preview how a deposit would divide across accounts by current income shares.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        amount: The deposit, in dollars, above 0.

    Returns:
        The split, summing to the amount, or `needs_shares` when nothing has a
        share.
    """
    return preview_deposit(db, user_id, amount)


@router.post("/{user_id}/deposits", response_model=list[Transaction], responses=responses["user_both"])
def add_deposit(user_id: VerifiedUserId, deposit: DepositCreate, db: DBSession):
    """Record incoming money spread across accounts, in one commit.

    Args:
        user_id: The verified caller's id.
        deposit: The amount, date, description and optional allocations.
        db: Request-scoped database session.

    Returns:
        The income rows written.

    Raises:
        HTTPException: 400 if there are no allocations and no account has an
            income share; 404 if an allocation names an account that is not one
            of the caller's unarchived accounts.
    """
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
    """Preview a tuition payment's arithmetic for the current term; writes nothing.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        cost_per_credit: The per-credit rate, 0 or more.
        fees: Fees belonging to no course, 0 or more.
        deductions_total: The deductions, summed, 0 or more.

    Returns:
        The preview, with the billable courses and both totals.
    """
    return preview_tuition(db, user_id, cost_per_credit, fees, deductions_total)


@router.post("/{user_id}/tuition", response_model=TuitionPayment, status_code=201, responses=responses["user_400"])
def create_tuition_payment(user_id: VerifiedUserId, data: TuitionCreate, db: DBSession):
    """Record a tuition payment: one ledger row plus what it was made of.

    Args:
        user_id: The verified caller's id.
        data: The account, date, rate, fees, description and deductions.
        db: Request-scoped database session.

    Returns:
        The recorded payment, with a 201.

    Raises:
        HTTPException: 400 if the account is not the caller's, there are no
            courses to charge a rate against, or the deductions leave nothing to
            pay.
    """
    try:
        return record_tuition(db, user_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{user_id}/courses/{course_id}/cost", response_model=CourseCost, responses=responses["course_both"])
def get_course_cost(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    """Get what a course cost: its gross share of tuition, plus what was bought for it.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        db: Request-scoped database session.

    Returns:
        The course's cost.

    Raises:
        HTTPException: 404 if the course is missing or not the caller's.
    """
    cost = course_cost(db, user_id, course_id)
    if cost is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return cost


@router.get("/{user_id}/tuition/{payment_id}", response_model=TuitionPayment, responses=responses["user_404"])
def read_tuition_payment(user_id: VerifiedUserId, payment_id: UUID, db: DBSession):
    """Get one of the caller's tuition payments.

    Args:
        user_id: The verified caller's id.
        payment_id: The payment.
        db: Request-scoped database session.

    Returns:
        The payment, with its deductions.

    Raises:
        HTTPException: 404 if the payment is missing or not the caller's.
    """
    payment = get_tuition(db, user_id, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Tuition payment not found")
    return payment


@router.patch("/{user_id}/tuition/{payment_id}", response_model=TuitionPayment, responses=responses["user_400"])
def edit_tuition_payment(
    user_id: VerifiedUserId, payment_id: UUID, data: TuitionUpdate, db: DBSession
):
    """Correct one of the caller's tuition payments, moving its ledger row to match.

    Args:
        user_id: The verified caller's id.
        payment_id: The payment.
        data: The full corrected payment.
        db: Request-scoped database session.

    Returns:
        The corrected payment.

    Raises:
        HTTPException: 400 if the account is not the caller's, the deductions
            exceed the bill, or nothing is left to pay; 404 if the payment is
            missing or not the caller's.
    """
    try:
        payment = update_tuition(db, user_id, payment_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payment is None:
        raise HTTPException(status_code=404, detail="Tuition payment not found")
    return payment


@router.delete("/{user_id}/tuition/{payment_id}", status_code=204, responses=responses["user_404"])
def remove_tuition_payment(user_id: VerifiedUserId, payment_id: UUID, db: DBSession):
    """Delete one of the caller's tuition payments and the ledger row it owns.

    Args:
        user_id: The verified caller's id.
        payment_id: The payment.
        db: Request-scoped database session.

    Returns:
        Nothing, with a 204.

    Raises:
        HTTPException: 404 if the payment is missing or not the caller's.
    """
    if delete_tuition(db, user_id, payment_id) is None:
        raise HTTPException(status_code=404, detail="Tuition payment not found")
    return None


@router.get("/{user_id}/term-budget", response_model=TermBudget, responses=responses["user_404"])
def get_term_budget(user_id: VerifiedUserId, db: DBSession):
    """Get what the current term has cost, over the term's own dates.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The term budget, or a reason when the term has no dates.
    """
    return term_budget(db, user_id)
