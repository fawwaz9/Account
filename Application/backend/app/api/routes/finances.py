from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Finances.schemas.account import Account, AccountCreate, AccountUpdate
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
from app.Finances.services.transaction_service import (
    create_transaction,
    create_transfer,
    delete_transaction,
    get_transaction,
    list_transactions,
    update_transaction,
)
from app.shared.errors import error_user, responses

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

    return removed


# ------------------------------------------------------------- transactions --

@router.get("/{user_id}/transactions", response_model=list[Transaction], responses=responses["user_404"])
def list_user_transactions(
    user_id: VerifiedUserId,
    db: DBSession,
    account_id: UUID | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    return list_transactions(db, user_id, account_id, limit)


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
def remove_transaction(user_id: VerifiedUserId, transaction_id: UUID, db: DBSession):
    removed = delete_transaction(db, user_id, transaction_id)
    if removed is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return removed
