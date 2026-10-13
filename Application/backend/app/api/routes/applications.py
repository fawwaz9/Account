"""The job application tracker (Phase 3 item 1), at /api/jobs/{user_id}/applications.

Single-user: another person's application answers 404, the same as one that
doesn't exist. `/stats` is declared above `/{application_id}`, or it would
parse as an id.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Jobs.schemas.application import Application, ApplicationIn, ApplicationStats, ApplicationUpdate, StepIn
from app.Jobs.services import application_service as service
from app.shared.errors import error_user, responses
from app.Usage.services.usage_service import CREATE, record as record_usage

router = APIRouter()

NOT_FOUND = "Application not found"
APP_404 = {404: {"description": NOT_FOUND}, 400: {"description": "Not allowed for this application"}}


@router.get("/{user_id}/applications", response_model=list[Application], responses=responses["user_404"])
def list_applications(user_id: VerifiedUserId, db: DBSession):
    found = service.list_applications(db, user_id)
    if found is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return found


@router.post("/{user_id}/applications", response_model=Application, responses=responses["user_404"])
def create_application(user_id: VerifiedUserId, body: ApplicationIn, db: DBSession):
    made = service.create(db, user_id, body)
    if made is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    record_usage(db, user_id, CREATE, "jobs")
    return made


@router.get("/{user_id}/applications/stats", response_model=ApplicationStats, responses=responses["user_404"])
def application_stats(user_id: VerifiedUserId, db: DBSession):
    found = service.stats(db, user_id)
    if found is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return found


@router.patch("/{user_id}/applications/{application_id}", response_model=Application, responses=APP_404)
def update_application(user_id: VerifiedUserId, application_id: UUID, body: ApplicationUpdate, db: DBSession):
    try:
        found = service.update(db, user_id, application_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if found is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return found


@router.delete("/{user_id}/applications/{application_id}", responses=APP_404)
def delete_application(user_id: VerifiedUserId, application_id: UUID, db: DBSession):
    if service.delete(db, user_id, application_id) is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return {"deleted": True}


@router.post("/{user_id}/applications/{application_id}/steps", response_model=Application, responses=APP_404)
def add_step(user_id: VerifiedUserId, application_id: UUID, body: StepIn, db: DBSession):
    try:
        found = service.add_step(db, user_id, application_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if found is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return found


@router.delete("/{user_id}/applications/{application_id}/steps/{step_id}", response_model=Application, responses=APP_404)
def delete_step(user_id: VerifiedUserId, application_id: UUID, step_id: UUID, db: DBSession):
    try:
        found = service.delete_step(db, user_id, application_id, step_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if found is None:
        raise HTTPException(status_code=404, detail="Step not found")
    return found
