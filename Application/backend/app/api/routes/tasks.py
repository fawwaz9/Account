from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Tasks.schemas.quick_capture import (
    QuickCapturePreview,
    QuickCaptureRequest,
    QuickCaptureResult,
)
from app.Tasks.schemas.recurring_task import (
    RecurringTask,
    RecurringTaskCreate,
    RecurringTaskRun,
    RecurringTaskUpdate,
)
from app.Tasks.schemas.task import Task, TaskCreate, TaskUpdate
from app.Tasks.services.recurring_task_service import (
    create_rule,
    delete_rule,
    get_rule,
    list_rules,
    run_due,
    skip_occurrence,
    update_rule,
)
from app.Tasks.services.quick_capture_service import build_preview, capture
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
REPEAT_404 = {404: {"description": "Repeating task not found"}}
REPEAT_BOTH = {**REPEAT_404, 400: {"description": "Invalid repeating task"}}


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


@router.get("/{user_id}/quick-capture", response_model=QuickCapturePreview, responses=responses["user_404"])
def preview_quick_capture(
    user_id: VerifiedUserId,
    db: DBSession,
    text: str = Query(..., min_length=1, max_length=300),
):
    """What one typed line would become, without writing anything.

    A read, so the client can call it as the student types and show the guess
    while it is still cheap to reword.
    """
    preview = build_preview(db, user_id, text)
    if preview is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return preview


@router.post("/{user_id}/quick-capture", response_model=QuickCaptureResult, responses=responses["user_both"])
def create_from_quick_capture(user_id: VerifiedUserId, request: QuickCaptureRequest, db: DBSession):
    """Create the task one line describes, and say how it was read."""
    try:
        task, preview = capture(db, user_id, request.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if task is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return QuickCaptureResult(task=task, preview=preview)


@router.get("/{user_id}/repeating", response_model=list[RecurringTask], responses=responses["user_404"])
def get_repeating(user_id: VerifiedUserId, db: DBSession, include_inactive: bool = True):
    rules = list_rules(db, user_id, include_inactive)
    if rules is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return rules


@router.post("/{user_id}/repeating", response_model=RecurringTask, responses=responses["user_both"])
def add_repeating(user_id: VerifiedUserId, rule: RecurringTaskCreate, db: DBSession):
    try:
        created = create_rule(db, user_id, rule)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return created


@router.post("/{user_id}/repeating/run", response_model=RecurringTaskRun, responses=responses["user_404"])
def run_repeating(user_id: VerifiedUserId, db: DBSession):
    """Write each repeating task's occurrences for the rolling window.

    Idempotent on (rule, due date), so calling it on every task or calendar load
    is safe, and is what makes a repeating chore simply be there with no
    scheduler running anywhere.
    """
    result = run_due(db, user_id)
    if result is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return result


@router.get("/{user_id}/repeating/{rule_id}", response_model=RecurringTask, responses=REPEAT_404)
def get_single_repeating(user_id: VerifiedUserId, rule_id: UUID, db: DBSession):
    rule = get_rule(db, user_id, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Repeating task not found")

    return rule


@router.patch("/{user_id}/repeating/{rule_id}", response_model=RecurringTask, responses=REPEAT_BOTH)
def edit_repeating(user_id: VerifiedUserId, rule_id: UUID, rule: RecurringTaskUpdate, db: DBSession):
    """Occurrences already written keep what they say; only later ones follow."""
    try:
        updated = update_rule(db, user_id, rule_id, rule)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="Repeating task not found")

    return updated


@router.delete("/{user_id}/repeating/{rule_id}", response_model=RecurringTask, responses=REPEAT_404)
def remove_repeating(
    user_id: VerifiedUserId,
    rule_id: UUID,
    db: DBSession,
    drop_pending: bool = Query(
        default=True, description="Also remove occurrences not yet ticked off"
    ),
):
    """Stop the repeat. Occurrences already done stay: they are a record."""
    deleted = delete_rule(db, user_id, rule_id, drop_pending)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Repeating task not found")

    audit.deletion("repeating_task", user_id=user_id, target_id=rule_id, detail=deleted.title)
    return deleted


@router.post("/{user_id}/repeating/{rule_id}/skip", response_model=RecurringTask, responses=REPEAT_404)
def skip_repeating(
    user_id: VerifiedUserId,
    rule_id: UUID,
    db: DBSession,
    on_date: date = Query(..., description="The occurrence to cancel"),
):
    """Cancel one occurrence without ending the repeat."""
    updated = skip_occurrence(db, user_id, rule_id, on_date)
    if updated is None:
        raise HTTPException(status_code=404, detail="Repeating task not found")

    return updated


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
