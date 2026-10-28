"""Task routes under /api/tasks: tasks, reminders, quick capture, repeats and timing.

Each handler parses the request, calls one Tasks service and maps its result to
a status: a service ValueError is a 400, a None is a 404. Literal paths are
declared above the `{task_id}` and `{reminder_id}` catch-alls they would
otherwise be parsed as.
"""

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
from app.Tasks.schemas.reminder import Reminder, ReminderCreate, ReminderUpdate
from app.Tasks.services.reminder_service import (
    create_reminder,
    delete_reminder,
    dismiss_reminder,
    due_reminders,
    list_reminders,
    update_reminder,
)
from app.Tasks.schemas.task import (
    EstimateRatio,
    SnoozeRequest,
    Task,
    TaskCreate,
    TaskSnooze,
    TaskUpdate,
    TimerStop,
)
from app.Tasks.schemas.timing import CompletionTiming
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
    snooze_history,
    snooze_task,
    start_task_timer,
    stop_task_timer,
    update_task,
    wake_task,
)
from app.Tasks.services.estimates_service import estimate_ratio
from app.Tasks.services.timing_service import completion_timing
from app.shared import audit
from app.shared.errors import error_user, responses
from app.Usage.services.usage_service import CREATE, record as record_usage

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
    include_snoozed: bool = Query(
        default=False, description="Also return tasks hidden until a later date"
    ),
    start: date | None = Query(default=None, description="Earliest due date, inclusive"),
    end: date | None = Query(default=None, description="Latest due date, inclusive"),
    course_id: UUID | None = None,
):
    """List the caller's tasks, most at risk and soonest due first, undated last.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        include_done: Also return ticked-off tasks.
        include_archived: Also return archived tasks.
        include_snoozed: Also return tasks hidden by a snooze until a later date.
        start: Earliest due date, inclusive; any bound leaves undated tasks out.
        end: Latest due date, inclusive.
        course_id: Only this course's tasks.

    Returns:
        The tasks, each with its course code and risk band.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    tasks = list_tasks(
        db,
        user_id,
        include_done=include_done,
        include_archived=include_archived,
        include_snoozed=include_snoozed,
        start=start,
        end=end,
        course_id=course_id,
    )
    if tasks is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return tasks


@router.post("/{user_id}/tasks", response_model=Task, responses=responses["user_both"])
def add_task(user_id: VerifiedUserId, task: TaskCreate, db: DBSession):
    """Create a task.

    Args:
        user_id: The verified caller's id.
        task: The task to create.
        db: Request-scoped database session.

    Returns:
        The created task.

    Raises:
        HTTPException: 400 if `course_id` is not one of the caller's courses; 404
            if the user does not exist.
    """
    try:
        created = create_task(db, user_id, task)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    record_usage(db, user_id, CREATE, "tasks")
    return created


@router.get(
    "/{user_id}/reminders",
    response_model=list[Reminder],
    responses=responses["user_404"],
)
def get_reminders(
    user_id: VerifiedUserId,
    db: DBSession,
    include_dismissed: bool = Query(
        default=False, description="Also return ones already acknowledged"
    ),
):
    """List the caller's reminders, earliest first.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        include_dismissed: Also return reminders already acknowledged.

    Returns:
        The reminders, each saying whether it is due.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    reminders = list_reminders(db, user_id, include_dismissed)
    if reminders is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return reminders


@router.post(
    "/{user_id}/reminders",
    response_model=Reminder,
    responses=responses["user_both"],
)
def add_reminder(user_id: VerifiedUserId, reminder: ReminderCreate, db: DBSession):
    """Create a reminder; `remind_at` is local wall time, sent without an offset.

    Args:
        user_id: The verified caller's id.
        reminder: The reminder to create.
        db: Request-scoped database session.

    Returns:
        The created reminder.

    Raises:
        HTTPException: 400 if `course_id` is not one of the caller's courses; 404
            if the user does not exist.
    """
    try:
        created = create_reminder(db, user_id, reminder)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return created


# Above /reminders/{reminder_id}, or "due" is parsed as an id.
@router.get(
    "/{user_id}/reminders/due",
    response_model=list[Reminder],
    responses=responses["user_404"],
)
def get_due_reminders(user_id: VerifiedUserId, db: DBSession):
    """List the reminders that should be on screen now, marking them as shown.

    A GET that writes: the first time a reminder is returned its `fired_at` is
    stamped, so it does not read as new on later loads.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        Undismissed reminders whose time has passed on the caller's clock.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    reminders = due_reminders(db, user_id)
    if reminders is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return reminders


@router.patch(
    "/{user_id}/reminders/{reminder_id}",
    response_model=Reminder,
    responses=TASK_BOTH,
)
def edit_reminder(
    user_id: VerifiedUserId,
    reminder_id: UUID,
    reminder: ReminderUpdate,
    db: DBSession,
):
    """Change the fields sent on one of the caller's reminders.

    Moving `remind_at` re-arms it: it counts as not yet shown, pushed or dismissed.

    Args:
        user_id: The verified caller's id.
        reminder_id: The reminder.
        reminder: The fields to change.
        db: Request-scoped database session.

    Returns:
        The updated reminder.

    Raises:
        HTTPException: 400 if `course_id` is not one of the caller's courses; 404
            if the reminder is missing or not the caller's.
    """
    try:
        updated = update_reminder(db, user_id, reminder_id, reminder)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="Reminder not found")

    return updated


@router.post(
    "/{user_id}/reminders/{reminder_id}/dismiss",
    response_model=Reminder,
    responses=TASK_404,
)
def acknowledge_reminder(user_id: VerifiedUserId, reminder_id: UUID, db: DBSession):
    """Dismiss one of the caller's reminders; the record stays.

    Args:
        user_id: The verified caller's id.
        reminder_id: The reminder.
        db: Request-scoped database session.

    Returns:
        The reminder, dismissed.

    Raises:
        HTTPException: 404 if the reminder is missing or not the caller's.
    """
    dismissed = dismiss_reminder(db, user_id, reminder_id)
    if dismissed is None:
        raise HTTPException(status_code=404, detail="Reminder not found")

    return dismissed


@router.delete(
    "/{user_id}/reminders/{reminder_id}",
    response_model=Reminder,
    responses=TASK_404,
)
def remove_reminder(user_id: VerifiedUserId, reminder_id: UUID, db: DBSession):
    """Delete one of the caller's reminders.

    Args:
        user_id: The verified caller's id.
        reminder_id: The reminder.
        db: Request-scoped database session.

    Returns:
        A copy of the deleted reminder.

    Raises:
        HTTPException: 404 if the reminder is missing or not the caller's.
    """
    deleted = delete_reminder(db, user_id, reminder_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Reminder not found")

    audit.deletion("reminder", user_id=user_id, target_id=reminder_id, detail=deleted.title)
    return deleted


@router.get("/{user_id}/quick-capture", response_model=QuickCapturePreview, responses=responses["user_404"])
def preview_quick_capture(
    user_id: VerifiedUserId,
    db: DBSession,
    text: str = Query(..., min_length=1, max_length=300),
):
    """Show what one typed line would become, without writing anything.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        text: The typed line, 1-300 characters.

    Returns:
        The reading: title, date, estimate and matched course.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    preview = build_preview(db, user_id, text)
    if preview is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return preview


@router.post("/{user_id}/quick-capture", response_model=QuickCaptureResult, responses=responses["user_both"])
def create_from_quick_capture(user_id: VerifiedUserId, request: QuickCaptureRequest, db: DBSession):
    """Create the task one typed line describes, and say how it was read.

    Args:
        user_id: The verified caller's id.
        request: The typed line.
        db: Request-scoped database session.

    Returns:
        The created task and the reading it came from.

    Raises:
        HTTPException: 400 if nothing is left of the line to make a title from; 404
            if the user does not exist.
    """
    try:
        task, preview = capture(db, user_id, request.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if task is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    record_usage(db, user_id, CREATE, "tasks")
    return QuickCaptureResult(task=task, preview=preview)


@router.get("/{user_id}/repeating", response_model=list[RecurringTask], responses=responses["user_404"])
def get_repeating(user_id: VerifiedUserId, db: DBSession, include_inactive: bool = True):
    """List the caller's repeating tasks, by start date.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        include_inactive: Also return paused ones (the default).

    Returns:
        The repeating tasks, each with its next occurrence due.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    rules = list_rules(db, user_id, include_inactive)
    if rules is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return rules


@router.post("/{user_id}/repeating", response_model=RecurringTask, responses=responses["user_both"])
def add_repeating(user_id: VerifiedUserId, rule: RecurringTaskCreate, db: DBSession):
    """Create a repeating task; its occurrences for the window are written at once.

    Args:
        user_id: The verified caller's id.
        rule: The rule and the template every occurrence is stamped from.
        db: Request-scoped database session.

    Returns:
        The created repeating task.

    Raises:
        HTTPException: 400 if `course_id` is not one of the caller's courses; 404
            if the user does not exist.
    """
    try:
        created = create_rule(db, user_id, rule)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return created


@router.post("/{user_id}/repeating/run", response_model=RecurringTaskRun, responses=responses["user_404"])
def run_repeating(user_id: VerifiedUserId, db: DBSession):
    """Write any missing occurrences of the caller's repeating tasks.

    Idempotent, so the client calls it before every task load.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        How many occurrences were written, and the rows.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    result = run_due(db, user_id)
    if result is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return result


@router.get("/{user_id}/repeating/{rule_id}", response_model=RecurringTask, responses=REPEAT_404)
def get_single_repeating(user_id: VerifiedUserId, rule_id: UUID, db: DBSession):
    """Get one of the caller's repeating tasks.

    Args:
        user_id: The verified caller's id.
        rule_id: The repeating task.
        db: Request-scoped database session.

    Returns:
        The repeating task.

    Raises:
        HTTPException: 404 if it is missing or not the caller's.
    """
    rule = get_rule(db, user_id, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Repeating task not found")

    return rule


@router.patch("/{user_id}/repeating/{rule_id}", response_model=RecurringTask, responses=REPEAT_BOTH)
def edit_repeating(user_id: VerifiedUserId, rule_id: UUID, rule: RecurringTaskUpdate, db: DBSession):
    """Change a repeating task; its outstanding occurrences follow, done ones stay.

    Args:
        user_id: The verified caller's id.
        rule_id: The repeating task.
        rule: The fields to change.
        db: Request-scoped database session.

    Returns:
        The updated repeating task.

    Raises:
        HTTPException: 400 if the course is not the caller's or the repeat would end
            before it starts; 404 if it is missing or not the caller's.
    """
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
    """Stop a repeating task; occurrences already ticked off stay as a record.

    Args:
        user_id: The verified caller's id.
        rule_id: The repeating task.
        db: Request-scoped database session.
        drop_pending: Also delete occurrences not yet ticked off (the default).

    Returns:
        A copy of the deleted repeating task.

    Raises:
        HTTPException: 404 if it is missing or not the caller's.
    """
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
    """Cancel one occurrence of a repeating task without ending the repeat.

    Args:
        user_id: The verified caller's id.
        rule_id: The repeating task.
        db: Request-scoped database session.
        on_date: The occurrence to cancel.

    Returns:
        The repeating task, with the date skipped.

    Raises:
        HTTPException: 404 if it is missing or not the caller's.
    """
    updated = skip_occurrence(db, user_id, rule_id, on_date)
    if updated is None:
        raise HTTPException(status_code=404, detail="Repeating task not found")

    return updated


@router.get(
    "/{user_id}/tasks/timing",
    response_model=CompletionTiming,
    responses=responses["user_404"],
)
def get_task_timing(user_id: VerifiedUserId, db: DBSession):
    """Get how early or late the caller finished dated work, this week and this month.

    Declared above `/tasks/{task_id}` so "timing" is not parsed as a task id.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The past seven days and the month to date.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    timing = completion_timing(db, user_id)
    if timing is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return timing


@router.get(
    "/{user_id}/tasks/estimates",
    response_model=EstimateRatio,
    responses=responses["user_404"],
)
def get_estimate_ratio(user_id: VerifiedUserId, db: DBSession):
    """Get how long the caller's tasks really take against their estimates.

    Declared above `/tasks/{task_id}` for the same reason as the timing route.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The actual-to-estimated ratio, once enough tasks have both figures.
    """
    return estimate_ratio(db, user_id)


@router.post("/{user_id}/tasks/{task_id}/timer/start", response_model=Task, responses=TASK_BOTH)
def start_timer_on_task(user_id: VerifiedUserId, task_id: UUID, db: DBSession):
    """Start timing one of the caller's tasks; starting a running timer changes nothing.

    Args:
        user_id: The verified caller's id.
        task_id: The task.
        db: Request-scoped database session.

    Returns:
        The task, with its timer running.

    Raises:
        HTTPException: 400 if the task is already done; 404 if it is missing or not
            the caller's.
    """
    try:
        task = start_task_timer(db, user_id, task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/{user_id}/tasks/{task_id}/timer/stop", response_model=TimerStop, responses=TASK_404)
def stop_timer_on_task(user_id: VerifiedUserId, task_id: UUID, db: DBSession):
    """Stop a task's timer, adding the minutes unless it ran past twelve hours.

    Args:
        user_id: The verified caller's id.
        task_id: The task.
        db: Request-scoped database session.

    Returns:
        The task, the minutes added, and whether the timer was discarded.

    Raises:
        HTTPException: 404 if the task is missing or not the caller's.
    """
    stopped = stop_task_timer(db, user_id, task_id)
    if stopped is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return stopped


@router.get("/{user_id}/tasks/{task_id}", response_model=Task, responses=TASK_404)
def get_single_task(user_id: VerifiedUserId, task_id: UUID, db: DBSession):
    """Get one of the caller's tasks.

    Args:
        user_id: The verified caller's id.
        task_id: The task.
        db: Request-scoped database session.

    Returns:
        The task (with no risk band, which only list reads compute).

    Raises:
        HTTPException: 404 if the task is missing or not the caller's.
    """
    task = get_task(db, user_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return task


@router.patch("/{user_id}/tasks/{task_id}", response_model=Task, responses=TASK_BOTH)
def edit_task(user_id: VerifiedUserId, task_id: UUID, task: TaskUpdate, db: DBSession):
    """Change the fields sent on one of the caller's tasks, including ticking it off.

    `{"done": true}` stamps when it was finished, stops its timer and archives it.

    Args:
        user_id: The verified caller's id.
        task_id: The task.
        task: The fields to change.
        db: Request-scoped database session.

    Returns:
        The updated task.

    Raises:
        HTTPException: 400 if the course is not the caller's or a due time would be
            left without a due date; 404 if the task is missing or not the
            caller's.
    """
    try:
        updated = update_task(db, user_id, task_id, task)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return updated


@router.post(
    "/{user_id}/tasks/{task_id}/snooze",
    response_model=Task,
    responses=TASK_BOTH,
)
def postpone_task(
    user_id: VerifiedUserId,
    task_id: UUID,
    snooze: SnoozeRequest,
    db: DBSession,
):
    """Snooze a task until a date, recording why; its due date does not move.

    Args:
        user_id: The verified caller's id.
        task_id: The task.
        snooze: The date it reappears and an optional reason.
        db: Request-scoped database session.

    Returns:
        The snoozed task.

    Raises:
        HTTPException: 400 if the date is not after today or the task is done; 404
            if the task is missing or not the caller's.
    """
    try:
        snoozed = snooze_task(db, user_id, task_id, snooze)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if snoozed is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return snoozed


@router.delete(
    "/{user_id}/tasks/{task_id}/snooze",
    response_model=Task,
    responses=TASK_404,
)
def resume_task(user_id: VerifiedUserId, task_id: UUID, db: DBSession):
    """Bring a snoozed task back now; its snooze history stays.

    Args:
        user_id: The verified caller's id.
        task_id: The task.
        db: Request-scoped database session.

    Returns:
        The task.

    Raises:
        HTTPException: 404 if the task is missing or not the caller's.
    """
    woken = wake_task(db, user_id, task_id)
    if woken is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return woken


@router.get(
    "/{user_id}/tasks/{task_id}/snoozes",
    response_model=list[TaskSnooze],
    responses=TASK_404,
)
def get_snooze_history(user_id: VerifiedUserId, task_id: UUID, db: DBSession):
    """List every time one of the caller's tasks was snoozed, oldest first.

    Args:
        user_id: The verified caller's id.
        task_id: The task.
        db: Request-scoped database session.

    Returns:
        The snoozes, with their reasons.

    Raises:
        HTTPException: 404 if the task is missing or not the caller's.
    """
    history = snooze_history(db, user_id, task_id)
    if history is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return history


@router.delete("/{user_id}/tasks/{task_id}", response_model=Task, responses=TASK_404)
def remove_task(user_id: VerifiedUserId, task_id: UUID, db: DBSession):
    """Delete one of the caller's tasks.

    Args:
        user_id: The verified caller's id.
        task_id: The task.
        db: Request-scoped database session.

    Returns:
        A copy of the deleted task.

    Raises:
        HTTPException: 404 if the task is missing or not the caller's.
    """
    deleted = delete_task(db, user_id, task_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Task not found")

    audit.deletion("task", user_id=user_id, target_id=task_id, detail=deleted.title)
    return deleted
