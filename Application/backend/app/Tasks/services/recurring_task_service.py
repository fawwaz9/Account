"""Repeating tasks: the rule, and the occurrences it writes.

The third consumer of the recurrence engine, alongside class times and standing
payments. Where it sits between the two is worth stating, because the three are
deliberately not the same.

* A **class time** is never written out. Nothing hangs off an individual lecture,
  so the calendar expands the rule on read and stores one row per term.
* A **standing payment** is written only once it has happened, because a balance
  is the sum of its rows and a future payment in that sum is money wrongly gone.
* A **repeating task** is written for a window that runs a little way ahead. Each
  occurrence is ticked off separately -- this week's reading being done says
  nothing about next week's -- so a virtual occurrence has nowhere to keep that.
  And unlike a payment, an occurrence that has not happened yet costs nothing to
  have sitting there: seeing Monday's reading on Sunday, and ticking it early, is
  the point.

Materialising is idempotent on (recurring_id, due_date), so it is safe to call on
every task and calendar load, and there is no scheduler anywhere.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app._database.models import CourseModel, RecurringTaskModel, TaskModel, UserModel, utc_now
from app.Calendar.services.event_service import parse_date
from app.Calendar.utils.recurrence import occurrences
from app.Calendar.utils.rule_columns import apply_recurrence, recurrence_of, rule_of
from app.Tasks.schemas.recurring_task import (
    RecurringTask,
    RecurringTaskCreate,
    RecurringTaskRun,
    RecurringTaskUpdate,
)

#: How far ahead occurrences are written. Wide enough to fill the calendar's
#: month view and the task page's fortnight, so neither has to ask for more;
#: narrow enough that a daily chore is sixty rows rather than a standing
#: commitment to fill the table forever.
MATERIALISE_AHEAD_DAYS = 60

#: How far back a first run will reach. A repeating chore missed three months ago
#: is not work to do, it is noise -- unlike a missed payment, which really is
#: owed. So this is much shorter than the payment catch-up.
MATERIALISE_BEHIND_DAYS = 14


def today() -> date:
    return date.today()


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


def skipped_of(rule: RecurringTaskModel) -> list[date]:
    return [parse_date(value) for value in (rule.skipped_dates or [])]


def written_dates(db: Session, recurring_id: uuid.UUID) -> set[date]:
    """Occurrences already written, by their due date.

    (recurring_id, due_date) is the dedup key: one repeating task cannot produce
    two occurrences for the same day, however often the materialiser runs.
    """
    rows = (
        db.query(TaskModel.due_date)
        .filter(TaskModel.recurring_id == recurring_id)
        .distinct()
        .all()
    )
    return {row.due_date for row in rows}


def attach_rule(db: Session, rule: RecurringTaskModel, codes: dict[uuid.UUID, str] | None = None):
    """Expose the rule columns and the derived fields the schema declares."""
    rule.recurrence = recurrence_of(rule)
    rule.course_code = (codes or course_codes(db, rule.user_id)).get(rule.course_id)
    rule.next_due_on = next_due(db, rule)
    return rule


def next_due(db: Session, rule: RecurringTaskModel) -> date | None:
    """The first occurrence from today on that is not already done."""
    horizon = today()
    done = {
        row.due_date
        for row in db.query(TaskModel.due_date)
        .filter(TaskModel.recurring_id == rule.id, TaskModel.done.is_(True))
        .all()
    }
    upcoming = occurrences(
        rule_of(rule),
        rule.starts_on,
        horizon,
        horizon + timedelta(days=MATERIALISE_AHEAD_DAYS),
        skipped_of(rule),
    )
    for day in upcoming:
        if day not in done:
            return day
    return None


# --------------------------------------------------------------------- CRUD --

def list_rules(db: Session, user_id: uuid.UUID, include_inactive: bool = True):
    if not user_exists(db, user_id):
        return None

    query = db.query(RecurringTaskModel).filter(RecurringTaskModel.user_id == user_id)
    if not include_inactive:
        query = query.filter(RecurringTaskModel.active.is_(True))

    rules = query.order_by(RecurringTaskModel.starts_on).all()
    codes = course_codes(db, user_id)
    return [attach_rule(db, rule, codes) for rule in rules]


def get_rule(db: Session, user_id: uuid.UUID, rule_id: uuid.UUID):
    rule = (
        db.query(RecurringTaskModel)
        .filter(RecurringTaskModel.id == rule_id, RecurringTaskModel.user_id == user_id)
        .first()
    )
    return None if rule is None else attach_rule(db, rule)


def create_rule(db: Session, user_id: uuid.UUID, data: RecurringTaskCreate):
    if not user_exists(db, user_id):
        return None

    if data.course_id is not None and owned_course(db, user_id, data.course_id) is None:
        raise ValueError("Course not found")

    rule = RecurringTaskModel(
        id=uuid.uuid4(),
        user_id=user_id,
        course_id=data.course_id,
        title=data.title.strip(),
        notes=data.notes,
        due_time=data.due_time,
        estimated_minutes=data.estimated_minutes,
        tags=list(data.tags),
        starts_on=data.starts_on,
        skipped_dates=[],
        active=data.active,
        created_at=utc_now(),
    )
    apply_recurrence(rule, data.recurrence)

    db.add(rule)
    db.commit()
    db.refresh(rule)

    # Written straight away, so a chore set up on Sunday for Monday is visible
    # on Sunday rather than after the next unrelated page load.
    materialise(db, user_id, rule)
    db.commit()
    db.refresh(rule)
    return attach_rule(db, rule)


def update_rule(db: Session, user_id: uuid.UUID, rule_id: uuid.UUID, data: RecurringTaskUpdate):
    rule = get_rule(db, user_id, rule_id)
    if rule is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    recurrence = update_data.pop("recurrence", None)

    if update_data.get("course_id") is not None:
        if owned_course(db, user_id, update_data["course_id"]) is None:
            raise ValueError("Course not found")

    for key, value in update_data.items():
        setattr(rule, key, value)

    if recurrence is not None:
        apply_recurrence(rule, data.recurrence)

    if rule.recur_until is not None and rule.recur_until < rule.starts_on:
        raise ValueError("A repeat cannot end before it starts")

    # Occurrences already written keep whatever they say. Rewriting them would
    # reach into work the student may have already edited or ticked off, and a
    # renamed chore does not rename last week's completed one -- that is a record
    # of what was actually done.
    db.commit()
    db.refresh(rule)
    materialise(db, user_id, rule)
    db.commit()
    db.refresh(rule)
    return attach_rule(db, rule)


def delete_rule(db: Session, user_id: uuid.UUID, rule_id: uuid.UUID, drop_pending: bool = True):
    """Stop the repeat.

    Occurrences already ticked off stay: they are a record of work actually done.
    Ones still outstanding go by default, since they only existed because the
    repeat did and leaving them would strand chores nothing is maintaining.
    """
    rule = get_rule(db, user_id, rule_id)
    if rule is None:
        return None

    snapshot = RecurringTask.model_validate(rule)

    if drop_pending:
        db.query(TaskModel).filter(
            TaskModel.recurring_id == rule.id, TaskModel.done.is_(False)
        ).delete(synchronize_session=False)

    db.query(TaskModel).filter(TaskModel.recurring_id == rule.id).update(
        {TaskModel.recurring_id: None}, synchronize_session=False
    )

    db.delete(rule)
    db.commit()
    return snapshot


def skip_occurrence(db: Session, user_id: uuid.UUID, rule_id: uuid.UUID, on_date: date):
    """Cancel one occurrence -- a week the seminar did not run."""
    rule = get_rule(db, user_id, rule_id)
    if rule is None:
        return None

    skipped = set(skipped_of(rule))
    skipped.add(on_date)
    # Rewritten whole: SQLAlchemy does not track mutation inside a JSON column.
    rule.skipped_dates = sorted(day.isoformat() for day in skipped)

    # An occurrence already written for that day goes too, unless it is done --
    # cancelling next Monday should clear Monday's row, not leave it sitting
    # there with nothing behind it.
    db.query(TaskModel).filter(
        TaskModel.recurring_id == rule.id,
        TaskModel.due_date == on_date,
        TaskModel.done.is_(False),
    ).delete(synchronize_session=False)

    db.commit()
    db.refresh(rule)
    return attach_rule(db, rule)


# ------------------------------------------------------------ materialising --

def materialise(db: Session, user_id: uuid.UUID, rule: RecurringTaskModel) -> list[TaskModel]:
    """Write this rule's occurrences for the rolling window, skipping any already there."""
    if not rule.active:
        return []

    horizon = today()
    window_start = max(rule.starts_on, horizon - timedelta(days=MATERIALISE_BEHIND_DAYS))
    window_end = horizon + timedelta(days=MATERIALISE_AHEAD_DAYS)

    wanted = occurrences(
        rule_of(rule), rule.starts_on, window_start, window_end, skipped_of(rule)
    )
    already = written_dates(db, rule.id)

    created: list[TaskModel] = []
    for on_date in wanted:
        if on_date in already:
            continue

        task = TaskModel(
            id=uuid.uuid4(),
            user_id=user_id,
            course_id=rule.course_id,
            recurring_id=rule.id,
            title=rule.title,
            notes=rule.notes,
            due_date=on_date,
            due_time=rule.due_time,
            estimated_minutes=rule.estimated_minutes,
            tags=list(rule.tags or []),
            done=False,
            archived=False,
            created_at=utc_now(),
        )
        db.add(task)
        created.append(task)

    if created:
        db.flush()
    return created


def run_due(db: Session, user_id: uuid.UUID) -> RecurringTaskRun | None:
    """Materialise every active rule's window.

    Idempotent, so calling it on every task and calendar load is safe and is what
    makes a repeating chore simply be there without a scheduler.
    """
    if not user_exists(db, user_id):
        return None

    rules = (
        db.query(RecurringTaskModel)
        .filter(
            RecurringTaskModel.user_id == user_id,
            RecurringTaskModel.active.is_(True),
        )
        .all()
    )

    created: list[TaskModel] = []
    for rule in rules:
        created.extend(materialise(db, user_id, rule))

    if created:
        db.commit()
        for task in created:
            db.refresh(task)

    codes = course_codes(db, user_id)
    for task in created:
        task.course_code = codes.get(task.course_id)

    return RecurringTaskRun(created=len(created), tasks=created)
