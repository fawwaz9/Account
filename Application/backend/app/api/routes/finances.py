from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Finances.schemas.account import (
    Account,
    AccountActivity,
    AccountCreate,
    AccountUpdate,
)
from app.Finances.schemas.budget import (
    BudgetSummary,
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
)
from app.Finances.schemas.transaction import (
    Transaction,
    TransactionCreate,
    TransactionUpdate,
    TransferCreate,
)
from app.Finances.services.account_service import (
    create_account,
    delete_account,
    get_account,
    get_accounts,
    update_account,
)
from app.Finances.services.tuition_service import (
    billable_courses,
    course_cost,
    preview_tuition,
    record_tuition,
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
    set_target,
    update_category,
)
from app.Finances.services.activity_service import get_account_activity
from app.Finances.services.deposit_service import preview_deposit, record_deposit
from app.shared.errors import error_user, responses
from app.shared import audit

router = APIRouter()

ACCOUNT_404 = {404: {"description": "Account not found"}}
TRANSACTION_404 = {404: {"description": "Transaction not found"}}


# ----------------------------------------------------------------- accounts --

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
    activity = get_account_activity(db, user_id, account_id, month or date.today())
    if activity is None:
        raise HTTPException(status_code=404, detail="Account not found")

    return activity


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
    """Movements, newest first. `start`/`end` bound `occurred_on` inclusively."""
    return list_transactions(db, user_id, account_id, limit, start, end)


@router.post("/{user_id}/transactions", response_model=Transaction, responses=ACCOUNT_404)
def add_transaction(user_id: VerifiedUserId, transaction: TransactionCreate, db: DBSession):
    try:
        created = create_transaction(db, user_id, transaction)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail="Account not found")

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
    updated = update_transaction(db, user_id, transaction_id, transaction)
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


@router.get("/{user_id}/budget-summary", response_model=BudgetSummary, responses=responses["user_404"])
def budget_summary(user_id: VerifiedUserId, db: DBSession, month: date | None = None):
    """Planned against actual for a month, per account and per category."""
    summary = get_budget_summary(db, user_id, month or date.today())
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
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{user_id}/courses/{course_id}/cost", response_model=CourseCost, responses=responses["course_both"])
def get_course_cost(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    """What a course cost: its gross share of tuition, plus what was bought for it."""
    cost = course_cost(db, user_id, course_id)
    if cost is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return cost
