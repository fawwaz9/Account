from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Tasks.schemas.task import Task, TaskCreate, TaskUpdate
from app.Tasks.services.task_service import (
    create_task,
    delete_task,
    get_task,
    list_tasks,
    update_task,
)
from app.shared import audit
from app.shared.errors import error_user, responses

router = APIRouter()

TASK_404 = {404: {"description": "Task not found"}}
TASK_BOTH = {**TASK_404, 400: {"description": "Invalid task data"}}


@router.get("/{user_id}/tasks", response_model=list[Task], responses=responses["user_404"])
def get_tasks(
    user_id: VerifiedUserId,
    db: DBSession,
    include_done: bool = False,
    include_archived: bool = False,
    start: date | None = Query(default=None, description="Earliest due date, inclusive"),
    end: date | None = Query(default=None, description="Latest due date, inclusive"),
    course_id: UUID | None = None,
):
    """Outstanding tasks, soonest first; undated ones last.

    A `start`/`end` window bounds the due date and so excludes undated tasks,
    which is what the calendar wants when it asks for a week.
    """
    tasks = list_tasks(
        db,
        user_id,
        include_done=include_done,
        include_archived=include_archived,
        start=start,
        end=end,
        course_id=course_id,
    )
    if tasks is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return tasks


@router.post("/{user_id}/tasks", response_model=Task, responses=responses["user_both"])
def add_task(user_id: VerifiedUserId, task: TaskCreate, db: DBSession):
    try:
        created = create_task(db, user_id, task)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return created


@router.get("/{user_id}/tasks/{task_id}", response_model=Task, responses=TASK_404)
def get_single_task(user_id: VerifiedUserId, task_id: UUID, db: DBSession):
    task = get_task(db, user_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return task


@router.patch("/{user_id}/tasks/{task_id}", response_model=Task, responses=TASK_BOTH)
def edit_task(user_id: VerifiedUserId, task_id: UUID, task: TaskUpdate, db: DBSession):
    """Also how a task is checked off: `{"done": true}` archives it and stamps
    when it was finished."""
    try:
        updated = update_task(db, user_id, task_id, task)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return updated


@router.delete("/{user_id}/tasks/{task_id}", response_model=Task, responses=TASK_404)
def remove_task(user_id: VerifiedUserId, task_id: UUID, db: DBSession):
    deleted = delete_task(db, user_id, task_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Task not found")

    audit.deletion("task", user_id=user_id, target_id=task_id, detail=deleted.title)
    return deleted
