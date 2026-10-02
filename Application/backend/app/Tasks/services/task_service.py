"""Tasks: what is outstanding, what is done, and what a week actually costs.

A task with a due date is also a calendar item -- the calendar reads them
through `list_tasks` with a window rather than through a table of its own, so
there is one record of a deadline rather than two that can disagree.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

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
)
from app.Users.services.user_service import get_preferences
from app.shared.dates import user_today

#: How far below target a course has to be for each band, in percentage points.
#: Two thresholds rather than one, because "below target" covers both a course
#: you will pull back next week and one you are losing -- and a single badge on
#: both says nothing about which is which.
RISK_BANDS = ((10.0, "severe"), (5.0, "moderate"), (0.0, "mild"))

#: Sort order for the bands, worst first. Anything unbadged sorts last.
RISK_RANK = {"severe": 0, "moderate": 1, "mild": 2, None: 3}


def user_exists(db: Session, user_id: uuid.UUID) -> bool:
    return db.query(UserModel).filter(UserModel.id == user_id).first() is not None


def owned_course(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> CourseModel | None:
    return (
        db.query(CourseModel)
        .filter(CourseModel.id == course_id, CourseModel.user_id == user_id)
        .first()
    )


def course_codes(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, str]:
    rows = (
        db.query(CourseModel.id, CourseModel.code)
        .filter(CourseModel.user_id == user_id)
        .all()
    )
    return {row.id: row.code for row in rows}


def risk_band(gap: float) -> str:
    """Which band a course sitting `gap` points below its target falls in."""
    for threshold, band in RISK_BANDS:
        if gap > threshold:
            return band
    return "mild"


def course_risk(db: Session, user: UserModel) -> dict[uuid.UUID, str]:
    """Courses the student is behind on, and by how much.

    Only the current term, which is the rule the dashboard already applies to
    the same question: a past course below target is history rather than
    something tonight's work can move. A course with no marks yet has no
    standing to be behind on.

    One query, and it is the same one `course_codes` makes -- both are read per
    task list, so widening it beats issuing a second.
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
    """Label a task with its course code, and how far behind that course is.

    School work is categorised by course code rather than by a tag the student
    has to remember to type, so the code has to travel with the task. The risk
    band travels the same way and for the same reason: the client would
    otherwise need every course and the target rules to colour one row.
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
    return task


def sort_key(task: TaskModel):
    """Most at risk first, then soonest; undated tasks last.

    Risk leads and the date ordering is untouched beneath it, so a task from a
    course you are failing rises to the top of whichever group it is already in
    rather than the page being reorganised around risk. Two tasks from equally
    troubled courses still sort by when they are due.

    `date.max` rather than None so undated tasks sort after every dated one
    instead of raising on the comparison.
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
    """Outstanding tasks by default; `start`/`end` bound `due_date` inclusively.

    A window excludes undated tasks, since the calendar asking for a week means
    the week's deadlines rather than everything ever.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None

    query = db.query(TaskModel).filter(TaskModel.user_id == user_id)

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
    task = (
        db.query(TaskModel)
        .filter(TaskModel.id == task_id, TaskModel.user_id == user_id)
        .first()
    )
    if task is None:
        return None

    return attach_course_code(task, course_codes(db, user_id))


def create_task(db: Session, user_id: uuid.UUID, data: TaskCreate):
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
    """Check or uncheck a task, keeping `completed_at` in step.

    Completing also archives: a checked task's place is the record of the term,
    not the list of what is left. Unchecking brings it back out, since the
    common reason to uncheck is having checked the wrong row.
    """
    task.done = done
    if done:
        task.completed_at = utc_now()
        task.archived = True
    else:
        task.completed_at = None
        task.archived = False


def snooze_task(
    db: Session, user_id: uuid.UUID, task_id: uuid.UUID, data: SnoozeRequest
):
    """Hide a task until a date, and record why.

    `due_date` is deliberately untouched. Moving it would hide the deferral
    rather than record it, and would make every later question about lateness
    measure against a date the student picked instead of the one they were
    given -- which is exactly what the completion-timing figure depends on.
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
    """Bring a snoozed task back now.

    The history stays. Undoing a snooze does not undo having made it, and the
    pattern is what the history is for.
    """
    task = get_task(db, user_id, task_id)
    if task is None:
        return None

    task.snoozed_until = None
    db.commit()
    db.refresh(task)
    return attach_course_code(task, course_codes(db, user_id))


def snooze_history(db: Session, user_id: uuid.UUID, task_id: uuid.UUID):
    """Every time this task was pushed back, oldest first."""
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
