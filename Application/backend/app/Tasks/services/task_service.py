"""Service functions for tasks: listing, editing, ticking off, timing and snoozing.

A task with a due date is also a calendar item; the calendar reads tasks through
`list_tasks` with a window rather than keeping its own copy. Tasks from a
current-term course below target carry a risk band and lead their date group.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app._database.models import (
    CourseModel,
    TaskModel,
    TaskSnoozeModel,
    UserModel,
    utc_now,
)
from app.Grades.utils.terms import (
    CURRENT,
    course_result_grade,
    effective_target,
    term_bucket,
)
from app.Tasks.schemas.task import (
    SnoozeRequest,
    Task as TaskSchema,
    TaskCreate,
    TaskSnooze,
    TaskUpdate,
    TimerStop,
)
from app.Users.services.user_service import get_preferences
from app.Tasks.services.estimates_service import start_timer, stop_clock
from app.shared.dates import user_today

#: How far below target a course has to be for each band, in percentage points.
#: Two thresholds rather than one, because "below target" covers both a course
#: you will pull back next week and one you are losing -- and a single badge on
#: both says nothing about which is which.
RISK_BANDS = ((10.0, "severe"), (5.0, "moderate"), (0.0, "mild"))

#: Sort order for the bands, worst first. Anything unbadged sorts last.
RISK_RANK = {"severe": 0, "moderate": 1, "mild": 2, None: 3}


def user_exists(db: Session, user_id: uuid.UUID) -> bool:
    """Return whether a user row with this id exists.

    Args:
        db: Open database session.
        user_id: Id to look up.

    Returns:
        True when the user row exists.
    """
    return db.query(UserModel).filter(UserModel.id == user_id).first() is not None


def owned_course(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> CourseModel | None:
    """Return the user's course with this id, or None.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        course_id: The course to fetch.

    Returns:
        The course, or None when it is missing or another user's.
    """
    return (
        db.query(CourseModel)
        .filter(CourseModel.id == course_id, CourseModel.user_id == user_id)
        .first()
    )


def course_codes(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, str]:
    """Return the user's course ids mapped to their codes, for labelling tasks.

    Args:
        db: Open database session.
        user_id: Owner of the rows.

    Returns:
        Course id to code, for every course the user has.
    """
    rows = (
        db.query(CourseModel.id, CourseModel.code)
        .filter(CourseModel.user_id == user_id)
        .all()
    )
    return {row.id: row.code for row in rows}


def risk_band(gap: float) -> str:
    """Return the risk band for a course sitting `gap` points below its target.

    Args:
        gap: Percentage points below target; positive.

    Returns:
        "severe" above 10, "moderate" above 5, otherwise "mild".
    """
    for threshold, band in RISK_BANDS:
        if gap > threshold:
            return band
    return "mild"


def course_risk(db: Session, user: UserModel) -> dict[uuid.UUID, str]:
    """Return the user's current-term courses that are below target, with their band.

    Courses outside the current term, and courses with nothing marked yet, are
    never flagged.

    Args:
        db: Open database session.
        user: The user, for their term and default target.

    Returns:
        Course id to "mild", "moderate" or "severe"; courses at or above target
        are absent.
    """
    default_target = get_preferences(user).default_target_grade
    courses = db.query(CourseModel).filter(CourseModel.user_id == user.id).all()

    risks: dict[uuid.UUID, str] = {}
    for course in courses:
        if term_bucket(course, user.current_school_year, user.current_semester) != CURRENT:
            continue

        result = course_result_grade(course)
        if result is None:
            continue

        gap = effective_target(course, default_target) - result
        if gap > 0:
            risks[course.id] = risk_band(gap)

    return risks


def attach_course_code(
    task: TaskModel,
    codes: dict[uuid.UUID, str],
    risks: dict[uuid.UUID, str] | None = None,
) -> TaskModel:
    """Label a task row with the derived fields its response carries.

    Sets `course_code`, `risk`, `snooze_count`, `last_snooze_reason` and
    `shared_with` on the instance; nothing is written to the database.

    Args:
        task: The task row.
        codes: Course ids mapped to codes.
        risks: Course ids mapped to risk bands; None leaves `risk` unset (None).

    Returns:
        The same task row.
    """
    task.course_code = codes.get(task.course_id)
    task.risk = (risks or {}).get(task.course_id)

    # The count and the latest reason, not the rows: a list of tasks does not
    # need a term of snooze history travelling with it.
    history = sorted(
        task.snoozes or [], key=lambda row: row.snoozed_at or datetime.min
    )
    task.snooze_count = len(history)
    task.last_snooze_reason = history[-1].reason if history else None
    # Who else is on it (Phase 2 D23): their names, as copied when they joined.
    task.shared_with = [m.member_name for m in sorted(task.members or [], key=lambda m: m.joined_at)]
    return task


def sort_key(task: TaskModel):
    """Return a task's sort key: most at risk first, then soonest due, undated last.

    Ties fall back to due time and creation time; risk only lifts a task within its
    date ordering.

    Args:
        task: A task row, with `risk` attached when known.

    Returns:
        A tuple that sorts ascending into list order.
    """
    return (
        RISK_RANK.get(getattr(task, "risk", None), 3),
        task.due_date or date.max,
        task.due_time or datetime.min.time(),
        task.created_at or datetime.min,
    )


def list_tasks(
    db: Session,
    user_id: uuid.UUID,
    *,
    include_done: bool = False,
    include_archived: bool = False,
    include_snoozed: bool = False,
    start: date | None = None,
    end: date | None = None,
    course_id: uuid.UUID | None = None,
):
    """Return the user's tasks, most at risk and soonest due first.

    By default only open, unarchived, unsnoozed tasks are returned; a snooze whose
    date has come is over. Snoozes are judged by the user's local today.

    Args:
        db: Open database session.
        user_id: Whose tasks.
        include_done: Also return ticked-off tasks.
        include_archived: Also return archived tasks.
        include_snoozed: Also return tasks hidden by a snooze.
        start: Earliest due date to include; any bound excludes undated tasks.
        end: Latest due date to include, inclusive.
        course_id: Only tasks for this course.

    Returns:
        Task rows labelled by `attach_course_code`, risk included; None when the
        user does not exist.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None

    query = (
        db.query(TaskModel)
        .filter(TaskModel.user_id == user_id)
        .options(selectinload(TaskModel.members))
    )

    if not include_archived:
        query = query.filter(TaskModel.archived.is_(False))
    if not include_done:
        query = query.filter(TaskModel.done.is_(False))
    if not include_snoozed:
        # A snooze that has run out is simply gone: the task comes back on its
        # own, in the position its untouched due date puts it in.
        # Resolved once, before the filter: the student's own day, so a snooze
        # set for "tomorrow" does not expire six hours early in UTC.
        on_day = user_today(db, user_id)
        query = query.filter(
            or_(
                TaskModel.snoozed_until.is_(None),
                TaskModel.snoozed_until <= on_day,
            )
        )
    if course_id is not None:
        query = query.filter(TaskModel.course_id == course_id)
    if start is not None:
        query = query.filter(TaskModel.due_date.isnot(None), TaskModel.due_date >= start)
    if end is not None:
        query = query.filter(TaskModel.due_date.isnot(None), TaskModel.due_date <= end)

    tasks = query.all()
    codes = course_codes(db, user_id)
    risks = course_risk(db, user)

    # Attached before sorting, because the sort key reads the risk band off the
    # task rather than looking it up again per comparison.
    labelled = [attach_course_code(task, codes, risks) for task in tasks]
    labelled.sort(key=sort_key)
    return labelled


def get_task(db: Session, user_id: uuid.UUID, task_id: uuid.UUID):
    """Return one of the user's tasks, labelled, or None when it is not theirs.

    The row carries course codes, snoozes and members but no risk band.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        task_id: The task to fetch.

    Returns:
        The task row with its course code attached, or None.
    """
    task = (
        db.query(TaskModel)
        .filter(TaskModel.id == task_id, TaskModel.user_id == user_id)
        .first()
    )
    if task is None:
        return None

    return attach_course_code(task, course_codes(db, user_id))


def create_task(db: Session, user_id: uuid.UUID, data: TaskCreate):
    """Create a task for the user.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose task.
        data: The task; its title is stripped.

    Returns:
        The new task row, labelled; None when the user does not exist.

    Raises:
        ValueError: If `course_id` is not one of the user's courses.
    """
    if not user_exists(db, user_id):
        return None

    if data.course_id is not None and owned_course(db, user_id, data.course_id) is None:
        raise ValueError("Course not found")

    task = TaskModel(
        id=uuid.uuid4(),
        user_id=user_id,
        course_id=data.course_id,
        title=data.title.strip(),
        notes=data.notes,
        due_date=data.due_date,
        due_time=data.due_time,
        estimated_minutes=data.estimated_minutes,
        tags=list(data.tags),
        priority=data.priority,
        done=False,
        archived=False,
        created_at=utc_now(),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return attach_course_code(task, course_codes(db, user_id))


def update_task(db: Session, user_id: uuid.UUID, task_id: uuid.UUID, data: TaskUpdate):
    """Change the fields sent on one of the user's tasks.

    Sending `done` goes through `set_done`, so completion, the timer and archiving
    move together. Commits.

    Args:
        db: Open database session.
        user_id: Whose task.
        task_id: The task.
        data: The fields to change.

    Returns:
        The updated task row, labelled; None when it is not the user's.

    Raises:
        ValueError: If a new `course_id` is not one of the user's courses, or the
            task would be left with a due time and no due date.
    """
    task = get_task(db, user_id, task_id)
    if task is None:
        return None

    update_data = data.model_dump(exclude_unset=True)

    if update_data.get("course_id") is not None:
        if owned_course(db, user_id, update_data["course_id"]) is None:
            raise ValueError("Course not found")

    done = update_data.pop("done", None)
    if "title" in update_data and update_data["title"] is not None:
        update_data["title"] = update_data["title"].strip()

    for key, value in update_data.items():
        setattr(task, key, value)

    if done is not None:
        set_done(task, done)

    if task.due_time is not None and task.due_date is None:
        raise ValueError("A time of day needs a date to go with it")

    db.commit()
    db.refresh(task)
    return attach_course_code(task, course_codes(db, user_id))


def set_done(task: TaskModel, done: bool) -> None:
    """Tick a task off or reopen it, keeping `completed_at` and `archived` in step.

    Completing stops a running timer (keeping its minutes), stamps `completed_at`
    and archives the task; reopening clears both. Only changes the row; the caller
    commits.

    Args:
        task: The task row.
        done: True to complete, False to reopen.
    """
    task.done = done
    if done:
        stop_clock(task)  # a finished task keeps its timed minutes, not a running clock
        task.completed_at = utc_now()
        task.archived = True
    else:
        task.completed_at = None
        task.archived = False


def start_task_timer(db: Session, user_id: uuid.UUID, task_id: uuid.UUID):
    """Start the timer on one of the user's tasks.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose task.
        task_id: The task.

    Returns:
        The task row, labelled; None when it is not the user's.

    Raises:
        ValueError: If the task is already done.
    """
    task = get_task(db, user_id, task_id)
    if task is None:
        return None
    start_timer(task)
    db.commit()
    db.refresh(task)
    return attach_course_code(task, course_codes(db, user_id))


def stop_task_timer(db: Session, user_id: uuid.UUID, task_id: uuid.UUID) -> TimerStop | None:
    """Stop the timer on one of the user's tasks and record what it measured.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose task.
        task_id: The task.

    Returns:
        The task with the minutes added and whether the timer was discarded as
        untrustworthy; None when the task is not the user's.
    """
    task = get_task(db, user_id, task_id)
    if task is None:
        return None
    added, discarded = stop_clock(task)
    db.commit()
    db.refresh(task)
    return TimerStop(
        task=attach_course_code(task, course_codes(db, user_id)),
        added_minutes=added,
        discarded=discarded,
    )


def snooze_task(
    db: Session, user_id: uuid.UUID, task_id: uuid.UUID, data: SnoozeRequest
):
    """Hide one of the user's tasks until a date, and record why.

    The due date never moves; each snooze is kept as history. Commits.

    Args:
        db: Open database session.
        user_id: Whose task.
        task_id: The task.
        data: The date to hide it until and an optional reason.

    Returns:
        The task row, labelled; None when it is not the user's.

    Raises:
        ValueError: If the date is not after the user's today, or the task is
            already done.
    """
    task = get_task(db, user_id, task_id)
    if task is None:
        return None

    if data.until <= user_today(db, user_id):
        raise ValueError("Snooze until a date in the future")
    if task.done:
        raise ValueError("That task is already done")

    task.snoozed_until = data.until
    db.add(TaskSnoozeModel(
        id=uuid.uuid4(),
        task_id=task.id,
        snoozed_at=utc_now(),
        until=data.until,
        reason=data.reason,
    ))

    db.commit()
    db.refresh(task)
    return attach_course_code(task, course_codes(db, user_id))


def wake_task(db: Session, user_id: uuid.UUID, task_id: uuid.UUID):
    """Bring a snoozed task back now, keeping its snooze history.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose task.
        task_id: The task.

    Returns:
        The task row, labelled; None when it is not the user's.
    """
    task = get_task(db, user_id, task_id)
    if task is None:
        return None

    task.snoozed_until = None
    db.commit()
    db.refresh(task)
    return attach_course_code(task, course_codes(db, user_id))


def snooze_history(db: Session, user_id: uuid.UUID, task_id: uuid.UUID):
    """Return every snooze of one of the user's tasks, oldest first.

    Args:
        db: Open database session.
        user_id: Whose task.
        task_id: The task.

    Returns:
        The snoozes; None when the task is not the user's.
    """
    task = get_task(db, user_id, task_id)
    if task is None:
        return None

    rows = (
        db.query(TaskSnoozeModel)
        .filter(TaskSnoozeModel.task_id == task_id)
        .order_by(TaskSnoozeModel.snoozed_at)
        .all()
    )
    return [TaskSnooze.model_validate(row) for row in rows]


def delete_task(db: Session, user_id: uuid.UUID, task_id: uuid.UUID):
    """Delete one of the user's tasks.

    Its snoozes, members and invite links go with it. Commits.

    Args:
        db: Open database session.
        user_id: Whose task.
        task_id: The task.

    Returns:
        A copy of the deleted task; None when it is not the user's.
    """
    task = get_task(db, user_id, task_id)
    if task is None:
        return None

    # Detached before the delete: attaching the course code marked the instance
    # dirty, and deleting it in the same session would otherwise flush an UPDATE
    # for a row that no longer exists.
    snapshot = TaskSchema.model_validate(task)
    db.delete(task)
    db.commit()
    return snapshot
