"""Shared tasks (Phase 2 item 9a, D23), under /api/tasks beside the rest.

Two halves. The owner's routes hang off the owner's own task and read and
write only rows the owner holds. The member's routes reach someone else's
task, and do it only through the definer functions in ``sharing`` -- so a
task you are not on answers 404, the same as a task that does not exist.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Tasks.schemas.sharing import (
    NewTaskLink, SharedTask, SharedTaskUpdate, TaskInviteAccepted, TaskInvitePreview, TaskInviteToken,
    TaskSharing,
)
from app.Tasks.services import task_sharing_service as service
from app.shared import audit
from app.shared.errors import responses

router = APIRouter()

TASK_404 = {404: {"description": "Task not found"}}
NO_TASK = "Task not found"
NO_LINK = "That link has expired or been cancelled."


# ---------------------------------------------------------------- the owner --

@router.get("/{user_id}/tasks/{task_id}/sharing", response_model=TaskSharing, responses=TASK_404)
def get_sharing(user_id: VerifiedUserId, task_id: UUID, db: DBSession):
    found = service.sharing_of(db, user_id, task_id)
    if found is None:
        raise HTTPException(status_code=404, detail=NO_TASK)
    return found


@router.post("/{user_id}/tasks/{task_id}/sharing/link", response_model=NewTaskLink,
             responses={**TASK_404, 400: {"description": "This task can't be shared"}})
def make_link(user_id: VerifiedUserId, task_id: UUID, db: DBSession):
    try:
        link = service.new_link(db, user_id, task_id)
    except service.NotShareable as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if link is None:
        raise HTTPException(status_code=404, detail=NO_TASK)
    return link


@router.delete("/{user_id}/tasks/{task_id}/sharing/link", responses=TASK_404)
def cancel_link(user_id: VerifiedUserId, task_id: UUID, db: DBSession):
    if not service.cancel_link(db, user_id, task_id):
        raise HTTPException(status_code=404, detail=NO_TASK)
    return {"cancelled": True}


@router.delete("/{user_id}/tasks/{task_id}/sharing/members/{member_id}", responses=TASK_404)
def remove_member(user_id: VerifiedUserId, task_id: UUID, member_id: UUID, db: DBSession):
    if not service.remove_member(db, user_id, task_id, member_id):
        raise HTTPException(status_code=404, detail="Nobody by that id is on this task")
    audit.deletion("task_member", user_id=user_id, target_id=member_id, detail=str(task_id))
    return {"removed": True}


# --------------------------------------------------------------- the member --

@router.get("/{user_id}/shared-tasks", response_model=list[SharedTask], responses=responses["user_404"])
def get_shared_tasks(user_id: VerifiedUserId, db: DBSession):
    return service.shared_with_me(db, user_id)


@router.post("/{user_id}/shared-tasks/invites/preview", response_model=TaskInvitePreview,
             responses=responses["user_404"])
def preview_link(user_id: VerifiedUserId, body: TaskInviteToken, db: DBSession):
    """Whose task this link joins, before you accept. POST, so the token stays
    out of URLs and logs."""
    found = service.preview(db, user_id, body.token)
    if found is None:
        raise HTTPException(status_code=404, detail=NO_LINK)
    return found


@router.post("/{user_id}/shared-tasks/invites/accept", response_model=TaskInviteAccepted,
             responses=responses["user_404"])
def accept_link(user_id: VerifiedUserId, body: TaskInviteToken, db: DBSession):
    return TaskInviteAccepted(status=service.accept(db, user_id, body.token))


@router.patch("/{user_id}/shared-tasks/{task_id}", response_model=SharedTask,
              responses={**TASK_404, 422: {"description": "Invalid change"}})
def update_shared_task(user_id: VerifiedUserId, task_id: UUID, body: SharedTaskUpdate, db: DBSession):
    updated = service.update_shared(db, user_id, task_id, body)
    if updated is None:
        raise HTTPException(status_code=404, detail=NO_TASK)
    return updated


@router.delete("/{user_id}/shared-tasks/{task_id}", responses=TASK_404)
def leave_shared_task(user_id: VerifiedUserId, task_id: UUID, db: DBSession):
    if not service.leave(db, user_id, task_id):
        raise HTTPException(status_code=404, detail=NO_TASK)
    return {"left": True}
