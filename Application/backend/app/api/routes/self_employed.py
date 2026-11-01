"""Self-employed routes, under /api/jobs/{user_id}: clients, invoices and the year's figures.

Phase 4 item 15 (§13.12). Single-user: another person's client, invoice or account
answers 404, the same as a missing one. A service ValueError (a used invoice
number, a client with invoices, dates out of order) is a 400.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Jobs.schemas.self_employed import (
    Client, ClientIn, ClientUpdate, Invoice, InvoiceIn, InvoiceUpdate, PaidIn, SelfEmployment,
)
from app.Jobs.services import self_employed_service as service
from app.shared.errors import error_user, responses
from app.Usage.services.usage_service import CREATE, record as record_usage

router = APIRouter()

CLIENT_404 = {404: {"description": "Client not found"}, 400: {"description": "Not allowed for this client"}}
INVOICE_404 = {404: {"description": "Invoice, client or account not found"},
               400: {"description": "Not allowed for this invoice"}}


def _run(call):
    """Run a service call, mapping its refusals to statuses: not found 404, not allowed 400."""
    try:
        return call()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _user(found):
    if found is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return found


@router.get("/{user_id}/clients", response_model=list[Client], responses=responses["user_404"])
def list_clients(user_id: VerifiedUserId, db: DBSession):
    """List the caller's clients with their invoice totals, unarchived first.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    return _user(service.list_clients(db, user_id))


@router.post("/{user_id}/clients", response_model=Client, responses=responses["user_404"])
def create_client(user_id: VerifiedUserId, body: ClientIn, db: DBSession):
    """Add a client.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    made = _user(service.create_client(db, user_id, body))
    record_usage(db, user_id, CREATE, "jobs")
    return made


@router.patch("/{user_id}/clients/{client_id}", response_model=Client, responses=CLIENT_404)
def update_client(user_id: VerifiedUserId, client_id: UUID, body: ClientUpdate, db: DBSession):
    """Rename or archive one of the caller's clients.

    Raises:
        HTTPException: 404 if it isn't theirs.
    """
    return _run(lambda: service.update_client(db, user_id, client_id, body))


@router.delete("/{user_id}/clients/{client_id}", status_code=204, responses=CLIENT_404)
def delete_client(user_id: VerifiedUserId, client_id: UUID, db: DBSession):
    """Delete a client that has no invoices.

    Raises:
        HTTPException: 404 if it isn't theirs; 400 if it has invoices.
    """
    _run(lambda: service.delete_client(db, user_id, client_id))
    return Response(status_code=204)


@router.get("/{user_id}/invoices", response_model=list[Invoice], responses=responses["user_404"])
def list_invoices(user_id: VerifiedUserId, db: DBSession):
    """List the caller's invoices, latest issued first, each with its state.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    return _user(service.list_invoices(db, user_id))


@router.post("/{user_id}/invoices", response_model=Invoice, responses=INVOICE_404)
def create_invoice(user_id: VerifiedUserId, body: InvoiceIn, db: DBSession):
    """Record an invoice to one of the caller's clients.

    Raises:
        HTTPException: 404 if the user or the client isn't found; 400 if the
            number is already used.
    """
    made = _user(_run(lambda: service.create_invoice(db, user_id, body)))
    record_usage(db, user_id, CREATE, "jobs")
    return made


@router.patch("/{user_id}/invoices/{invoice_id}", response_model=Invoice, responses=INVOICE_404)
def update_invoice(user_id: VerifiedUserId, invoice_id: UUID, body: InvoiceUpdate, db: DBSession):
    """Correct one of the caller's invoices.

    Raises:
        HTTPException: 404 if the invoice or a new client isn't theirs; 400 for a
            used number or dates out of order.
    """
    return _run(lambda: service.update_invoice(db, user_id, invoice_id, body))


@router.delete("/{user_id}/invoices/{invoice_id}", status_code=204, responses=INVOICE_404)
def delete_invoice(user_id: VerifiedUserId, invoice_id: UUID, db: DBSession):
    """Delete one of the caller's invoices and any deposit its payment wrote.

    Raises:
        HTTPException: 404 if it isn't theirs.
    """
    _run(lambda: service.delete_invoice(db, user_id, invoice_id))
    return Response(status_code=204)


@router.post("/{user_id}/invoices/{invoice_id}/paid", response_model=Invoice, responses=INVOICE_404)
def mark_paid(user_id: VerifiedUserId, invoice_id: UUID, body: PaidIn, db: DBSession):
    """Mark an invoice paid, recording the payment in an account, split, or not at all.

    Raises:
        HTTPException: 404 if the invoice or account isn't theirs; 400 if paid
            before issue or a split has no income shares.
    """
    return _run(lambda: service.mark_paid(db, user_id, invoice_id, body))


@router.delete("/{user_id}/invoices/{invoice_id}/paid", response_model=Invoice, responses=INVOICE_404)
def mark_unpaid(user_id: VerifiedUserId, invoice_id: UUID, db: DBSession):
    """Mark an invoice unpaid again, deleting the deposit its payment wrote.

    Raises:
        HTTPException: 404 if it isn't theirs.
    """
    return _run(lambda: service.mark_unpaid(db, user_id, invoice_id))


@router.get("/{user_id}/self-employment", response_model=SelfEmployment, responses=responses["user_404"])
def self_employment(user_id: VerifiedUserId, db: DBSession,
                    year: int | None = Query(default=None, ge=2000, le=2100)):
    """Return a year of self-employment and the CRA rules read against it.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    return _user(service.self_employment(db, user_id, year))
