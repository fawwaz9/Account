"""Shared-task routes under /api/tasks: owner controls and the member's view.

The owner's routes act only on rows the owner holds. The member's routes reach
someone else's task only through the definer functions in `sharing`, so a task
the caller is not on answers 404 like a missing one.
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
    """Get who is on one of the caller's tasks and whether an invite link is open.

    Args:
        user_id: The verified caller's id.
        task_id: The task.
        db: Request-scoped database session.

    Returns:
        The members, the live link (without its token) and whether it can be shared.

    Raises:
        HTTPException: 404 if the task is missing or not the caller's.
    """
    found = service.sharing_of(db, user_id, task_id)
    if found is None:
        raise HTTPException(status_code=404, detail=NO_TASK)
    return found


@router.post("/{user_id}/tasks/{task_id}/sharing/link", response_model=NewTaskLink,
             responses={**TASK_404, 400: {"description": "This task can't be shared"}})
def make_link(user_id: VerifiedUserId, task_id: UUID, db: DBSession):
    """Make a new invite link for one of the caller's tasks, cancelling any live one.

    Args:
        user_id: The verified caller's id.
        task_id: The task.
        db: Request-scoped database session.

    Returns:
        The link's token, shown only this once, and when it expires.

    Raises:
        HTTPException: 400 if the task is an occurrence of a repeating task; 404 if
            the task is missing or not the caller's.
    """
    try:
        link = service.new_link(db, user_id, task_id)
    except service.NotShareable as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if link is None:
        raise HTTPException(status_code=404, detail=NO_TASK)
    return link


@router.delete("/{user_id}/tasks/{task_id}/sharing/link", responses=TASK_404)
def cancel_link(user_id: VerifiedUserId, task_id: UUID, db: DBSession):
    """Cancel any live invite link on one of the caller's tasks.

    Args:
        user_id: The verified caller's id.
        task_id: The task.
        db: Request-scoped database session.

    Returns:
        `{"cancelled": true}`, including when no link was open.

    Raises:
        HTTPException: 404 if the task is missing or not the caller's.
    """
    if not service.cancel_link(db, user_id, task_id):
        raise HTTPException(status_code=404, detail=NO_TASK)
    return {"cancelled": True}


@router.delete("/{user_id}/tasks/{task_id}/sharing/members/{member_id}", responses=TASK_404)
def remove_member(user_id: VerifiedUserId, task_id: UUID, member_id: UUID, db: DBSession):
    """Take someone off one of the caller's tasks.

    Args:
        user_id: The verified caller's id.
        task_id: The task.
        member_id: The membership's id, as `get_sharing` lists it.
        db: Request-scoped database session.

    Returns:
        `{"removed": true}`.

    Raises:
        HTTPException: 404 if the task is not the caller's or has no such member.
    """
    if not service.remove_member(db, user_id, task_id, member_id):
        raise HTTPException(status_code=404, detail="Nobody by that id is on this task")
    audit.deletion("task_member", user_id=user_id, target_id=member_id, detail=str(task_id))
    return {"removed": True}


# --------------------------------------------------------------- the member --

@router.get("/{user_id}/shared-tasks", response_model=list[SharedTask], responses=responses["user_404"])
def get_shared_tasks(user_id: VerifiedUserId, db: DBSession):
    """List other people's tasks the caller has joined, open ones first.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The member's view of each task; empty when there are none.
    """
    return service.shared_with_me(db, user_id)


@router.post("/{user_id}/shared-tasks/invites/preview", response_model=TaskInvitePreview,
             responses=responses["user_404"])
def preview_link(user_id: VerifiedUserId, body: TaskInviteToken, db: DBSession):
    """See whose task an invite link joins, before accepting it.

    POST so the token stays out of URLs and logs.

    Args:
        user_id: The verified caller's id.
        body: The token from the link.
        db: Request-scoped database session.

    Returns:
        The owner's name and the task's title.

    Raises:
        HTTPException: 404 if the link is unknown, expired or cancelled.
    """
    found = service.preview(db, user_id, body.token)
    if found is None:
        raise HTTPException(status_code=404, detail=NO_LINK)
    return found


@router.post("/{user_id}/shared-tasks/invites/accept", response_model=TaskInviteAccepted,
             responses=responses["user_404"])
def accept_link(user_id: VerifiedUserId, body: TaskInviteToken, db: DBSession):
    """Join someone else's task through an invite link.

    Args:
        user_id: The verified caller's id.
        body: The token from the link.
        db: Request-scoped database session.

    Returns:
        The outcome: "accepted", "invalid", "own", "already" or "full".
    """
    return TaskInviteAccepted(status=service.accept(db, user_id, body.token))


@router.patch("/{user_id}/shared-tasks/{task_id}", response_model=SharedTask,
              responses={**TASK_404, 422: {"description": "Invalid change"}})
def update_shared_task(user_id: VerifiedUserId, task_id: UUID, body: SharedTaskUpdate, db: DBSession):
    """Tick off, or edit the title and notes of, a task the caller is a member of.

    Args:
        user_id: The verified caller's id.
        task_id: The shared task.
        body: The fields to change.
        db: Request-scoped database session.

    Returns:
        The task as the member now sees it.

    Raises:
        HTTPException: 404 if the caller is not on the task.
    """
    updated = service.update_shared(db, user_id, task_id, body)
    if updated is None:
        raise HTTPException(status_code=404, detail=NO_TASK)
    return updated


@router.delete("/{user_id}/shared-tasks/{task_id}", responses=TASK_404)
def leave_shared_task(user_id: VerifiedUserId, task_id: UUID, db: DBSession):
    """Leave someone else's task the caller is on.

    Args:
        user_id: The verified caller's id.
        task_id: The task.
        db: Request-scoped database session.

    Returns:
        `{"left": true}`.

    Raises:
        HTTPException: 404 if the caller is not on the task.
    """
    if not service.leave(db, user_id, task_id):
        raise HTTPException(status_code=404, detail=NO_TASK)
    return {"left": True}
