"""Standing-instruction routes under /api/finances: rules, catch-up and upcoming.

A standing instruction stores a rule; its payments become ledger rows only once
due, through the catch-up the client runs on every budget load. Literal paths
(`/run`, `/upcoming`) are declared above `/{rule_id}`.
"""

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
    """List the caller's standing instructions, by start date.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        include_inactive: Also return paused ones (the default).

    Returns:
        The instructions, each with its last and next payment dates.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    rules = list_rules(db, user_id, include_inactive)
    if rules is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return rules


@router.post("/{user_id}/recurring", response_model=RecurringTransaction, responses=responses["user_both"])
def add_rule(user_id: VerifiedUserId, rule: RecurringCreate, db: DBSession):
    """Create a standing instruction; nothing reaches the ledger until a payment is due.

    Args:
        user_id: The verified caller's id.
        rule: The instruction.
        db: Request-scoped database session.

    Returns:
        The created instruction.

    Raises:
        HTTPException: 400 if an account or the category is not the caller's; 404
            if the user does not exist.
    """
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
    """Write every standing-instruction payment that is owed and not yet written.

    Idempotent on (rule, date), so the client calls it on every budget load.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        through: The last date that counts as due; defaults to the caller's today.
            Nothing stops a later date, which writes future payments as real rows.

    Returns:
        How many rows were written, the rows, and any rules that could not run.

    Raises:
        HTTPException: 404 if the user does not exist.
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
    """List the payments the caller's rules say are coming in a window, as projections.

    Nothing here is a ledger row; it is what safe-to-spend subtracts.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        start: First date of the window, inclusive.
        end: Last date of the window, inclusive.

    Returns:
        The projected charges, by date.

    Raises:
        HTTPException: 400 if the window is inverted or longer than 400 days; 404
            if the user does not exist.
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
    """Get one of the caller's standing instructions.

    Args:
        user_id: The verified caller's id.
        rule_id: The instruction.
        db: Request-scoped database session.

    Returns:
        The instruction.

    Raises:
        HTTPException: 404 if it is missing or not the caller's.
    """
    rule = get_rule(db, user_id, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Standing instruction not found")

    return rule


@router.patch("/{user_id}/recurring/{rule_id}", response_model=RecurringTransaction, responses=RULE_BOTH)
def edit_rule(user_id: VerifiedUserId, rule_id: UUID, rule: RecurringUpdate, db: DBSession):
    """Change the fields sent on one of the caller's standing instructions.

    Payments already written are left alone.

    Args:
        user_id: The verified caller's id.
        rule_id: The instruction.
        rule: The fields to change.
        db: Request-scoped database session.

    Returns:
        The updated instruction.

    Raises:
        HTTPException: 400 if a category is set on anything but an expense or is
            not the caller's, or the repeat would end before it starts; 404 if it
            is missing or not the caller's.
    """
    try:
        updated = update_rule(db, user_id, rule_id, rule)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="Standing instruction not found")

    return updated


@router.delete("/{user_id}/recurring/{rule_id}", response_model=RecurringTransaction, responses=RULE_404)
def remove_rule(user_id: VerifiedUserId, rule_id: UUID, db: DBSession):
    """Stop a standing instruction; payments it already made stay in the ledger.

    Args:
        user_id: The verified caller's id.
        rule_id: The instruction.
        db: Request-scoped database session.

    Returns:
        A copy of the deleted instruction.

    Raises:
        HTTPException: 404 if it is missing or not the caller's.
    """
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
    """Skip one payment of a standing instruction without ending it.

    Args:
        user_id: The verified caller's id.
        rule_id: The instruction.
        db: Request-scoped database session.
        on_date: The payment date to skip.

    Returns:
        The instruction, with the date skipped.

    Raises:
        HTTPException: 404 if it is missing or not the caller's.
    """
    updated = skip_occurrence(db, user_id, rule_id, on_date)
    if updated is None:
        raise HTTPException(status_code=404, detail="Standing instruction not found")

    return updated
