"""Accountability partners and invite links (Phase 2 item 10, D16, D22)."""
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


@router.get("/{user_id}", response_model=Partners, responses=responses["user_404"])
def get_partners(user_id: VerifiedUserId, db: DBSession):
    found = partner_service.overview(db, user_id)
    if found is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return found


@router.post("/{user_id}/invites", response_model=NewInvite, responses=responses["user_404"])
def create_invite(user_id: VerifiedUserId, db: DBSession):
    try:
        invite = partner_service.create_invite(db, user_id)
    except partner_service.InviteLimit as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if invite is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return invite


@router.delete("/{user_id}/invites/{invite_id}", responses=responses["user_404"])
def revoke_invite(user_id: VerifiedUserId, invite_id: UUID, db: DBSession):
    if not partner_service.revoke_invite(db, user_id, invite_id):
        raise HTTPException(status_code=404, detail="No open invite with that id")
    return {"revoked": True}


@router.post("/{user_id}/invites/preview", response_model=InvitePreviewOut, responses=responses["user_404"])
def preview_invite(user_id: VerifiedUserId, body: InviteToken, db: DBSession):
    """Who sent this link, before you accept it. POST, so the token stays out
    of URLs and logs."""
    found = partner_service.preview(db, user_id, body.token)
    if found is None:
        raise HTTPException(status_code=404, detail=NO_INVITE)
    return InvitePreviewOut(inviter_name=found.inviter_name, kind=found.kind)


@router.post("/{user_id}/invites/accept", response_model=AcceptResult, responses=responses["user_404"])
def accept_invite(user_id: VerifiedUserId, body: InviteToken, db: DBSession):
    return AcceptResult(status=partner_service.accept(db, user_id, body.token))


@router.delete("/{user_id}/partners/{partner_id}", responses=responses["user_404"])
def end_partnership(user_id: VerifiedUserId, partner_id: UUID, db: DBSession):
    if not partner_service.end(db, user_id, partner_id):
        raise HTTPException(status_code=404, detail="No partnership with that person")
    return {"ended": True}
