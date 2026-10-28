"""Accountability partner routes under `/api/partners`: panel, invites, partners."""
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Partners.schemas.partner import (
    AcceptResult, InvitePreviewOut, InviteToken, NewInvite, Partners,
)
from app.Partners.services import partner_service
from app.shared.errors import error_user, responses

router = APIRouter()

NO_INVITE = "That invite link has expired, been used, or been cancelled."
"""The one answer for any invite link that cannot be used."""


@router.get("/{user_id}", response_model=Partners, responses=responses["user_404"])
def get_partners(user_id: VerifiedUserId, db: DBSession):
    """Return the partners panel: the caller's figure, each partner's, and open invites.

    Refreshes the caller's own figure as a side effect.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The panel.

    Raises:
        HTTPException: 404 when the user does not exist.
    """
    found = partner_service.overview(db, user_id)
    if found is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return found


@router.post("/{user_id}/invites", response_model=NewInvite, responses=responses["user_404"])
def create_invite(user_id: VerifiedUserId, db: DBSession):
    """Create a partner invite link; the token in the response is shown only this once.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The invite's id, token and expiry.

    Raises:
        HTTPException: 400 when the caller already has five open invites; 404 when the
            user does not exist.
    """
    try:
        invite = partner_service.create_invite(db, user_id)
    except partner_service.InviteLimit as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if invite is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return invite


@router.delete("/{user_id}/invites/{invite_id}", responses=responses["user_404"])
def revoke_invite(user_id: VerifiedUserId, invite_id: UUID, db: DBSession):
    """Cancel one of the caller's unused invites.

    Args:
        user_id: The verified caller's id.
        invite_id: The invite.
        db: Request-scoped database session.

    Returns:
        `{"revoked": true}`.

    Raises:
        HTTPException: 404 when there is no unused invite of the caller's with that id.
    """
    if not partner_service.revoke_invite(db, user_id, invite_id):
        raise HTTPException(status_code=404, detail="No open invite with that id")
    return {"revoked": True}


@router.post("/{user_id}/invites/preview", response_model=InvitePreviewOut, responses=responses["user_404"])
def preview_invite(user_id: VerifiedUserId, body: InviteToken, db: DBSession):
    """Return who sent an invite link, before accepting it.

    A POST, so the token stays out of URLs and logs.

    Args:
        user_id: The verified caller's id.
        body: The token from the link.
        db: Request-scoped database session.

    Returns:
        The inviter's name and the invite's kind.

    Raises:
        HTTPException: 404 when the link is unknown, used, revoked or expired.
    """
    found = partner_service.preview(db, user_id, body.token)
    if found is None:
        raise HTTPException(status_code=404, detail=NO_INVITE)
    return InvitePreviewOut(inviter_name=found.inviter_name, kind=found.kind)


@router.post("/{user_id}/invites/accept", response_model=AcceptResult, responses=responses["user_404"])
def accept_invite(user_id: VerifiedUserId, body: InviteToken, db: DBSession):
    """Accept a partner invite, creating the partnership on both sides.

    Args:
        user_id: The verified caller's id.
        body: The token from the link.
        db: Request-scoped database session.

    Returns:
        `status`: "accepted", "invalid", "own" or "already".
    """
    return AcceptResult(status=partner_service.accept(db, user_id, body.token))


@router.delete("/{user_id}/partners/{partner_id}", responses=responses["user_404"])
def end_partnership(user_id: VerifiedUserId, partner_id: UUID, db: DBSession):
    """End a partnership from either side, removing both rows.

    Args:
        user_id: The verified caller's id.
        partner_id: The partner.
        db: Request-scoped database session.

    Returns:
        `{"ended": true}`.

    Raises:
        HTTPException: 404 when there is no partnership with that person.
    """
    if not partner_service.end(db, user_id, partner_id):
        raise HTTPException(status_code=404, detail="No partnership with that person")
    return {"ended": True}
