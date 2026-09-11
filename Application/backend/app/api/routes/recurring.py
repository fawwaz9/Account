from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Finances.schemas.recurring import (
    RecurringCreate,
    RecurringRun,
    RecurringTransaction,
    RecurringUpdate,
    UpcomingCharge,
)
from app.Finances.services.recurring_service import (
    create_rule,
    delete_rule,
    get_rule,
    list_rules,
    run_due,
    skip_occurrence,
    upcoming,
    update_rule,
)
from app.shared import audit
from app.shared.errors import error_user, responses

router = APIRouter()

RULE_404 = {404: {"description": "Standing instruction not found"}}
RULE_BOTH = {**RULE_404, 400: {"description": "Invalid standing instruction"}}


@router.get("/{user_id}/recurring", response_model=list[RecurringTransaction], responses=responses["user_404"])
def get_rules(user_id: VerifiedUserId, db: DBSession, include_inactive: bool = True):
    rules = list_rules(db, user_id, include_inactive)
    if rules is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return rules


@router.post("/{user_id}/recurring", response_model=RecurringTransaction, responses=responses["user_both"])
def add_rule(user_id: VerifiedUserId, rule: RecurringCreate, db: DBSession):
    try:
        created = create_rule(db, user_id, rule)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return created


@router.post("/{user_id}/recurring/run", response_model=RecurringRun, responses=responses["user_404"])
def run_recurring(
    user_id: VerifiedUserId,
    db: DBSession,
    through: date | None = Query(default=None, description="Defaults to today"),
):
    """Write every payment that is owed and has not been written yet.

    Idempotent, because a payment is keyed by (rule, date): calling it on every
    budget load is safe, and is what makes last month's rent already be there
    when you open the app, with no scheduler to run.
    """
    result = run_due(db, user_id, through)
    if result is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return result


@router.get("/{user_id}/recurring/upcoming", response_model=list[UpcomingCharge], responses=responses["user_both"])
def get_upcoming(
    user_id: VerifiedUserId,
    db: DBSession,
    start: date = Query(..., description="First date of the window, inclusive"),
    end: date = Query(..., description="Last date of the window, inclusive"),
):
    """Commitments ahead: what the rules say is coming but has not happened.

    Projections, never rows. Nothing here has moved money, so nothing here
    belongs in a balance -- it is what a "safe to spend" figure subtracts.
    """
    try:
        charges = upcoming(db, user_id, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if charges is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return charges


@router.get("/{user_id}/recurring/{rule_id}", response_model=RecurringTransaction, responses=RULE_404)
def get_single_rule(user_id: VerifiedUserId, rule_id: UUID, db: DBSession):
    rule = get_rule(db, user_id, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Standing instruction not found")

    return rule


@router.patch("/{user_id}/recurring/{rule_id}", response_model=RecurringTransaction, responses=RULE_BOTH)
def edit_rule(user_id: VerifiedUserId, rule_id: UUID, rule: RecurringUpdate, db: DBSession):
    try:
        updated = update_rule(db, user_id, rule_id, rule)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="Standing instruction not found")

    return updated


@router.delete("/{user_id}/recurring/{rule_id}", response_model=RecurringTransaction, responses=RULE_404)
def remove_rule(user_id: VerifiedUserId, rule_id: UUID, db: DBSession):
    """Stops the instruction. Payments it already made stay: they are real."""
    deleted = delete_rule(db, user_id, rule_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Standing instruction not found")

    audit.deletion(
        "recurring", user_id=user_id, target_id=rule_id,
        detail=deleted.description or deleted.kind,
    )
    return deleted


@router.post("/{user_id}/recurring/{rule_id}/skip", response_model=RecurringTransaction, responses=RULE_404)
def skip_one(
    user_id: VerifiedUserId,
    rule_id: UUID,
    db: DBSession,
    on_date: date = Query(..., description="The payment to skip"),
):
    """Skip one payment without ending the instruction."""
    updated = skip_occurrence(db, user_id, rule_id, on_date)
    if updated is None:
        raise HTTPException(status_code=404, detail="Standing instruction not found")

    return updated
