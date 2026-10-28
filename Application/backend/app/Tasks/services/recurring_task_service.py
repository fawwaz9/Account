"""Service functions for repeating tasks: the rule, and the occurrences it writes.

Unlike class times (expanded on read) and standing payments (written once
paid), a repeating task writes a real task per occurrence for a rolling window,
14 days back to 60 ahead, so each one can be ticked off on its own.
Materialising is idempotent on (recurring_id, occurrence_date) and runs on every
Tasks page load; there is no scheduler.

`occurrence_date` is an occurrence's identity and never changes; `due_date` is
where it currently sits and the student may move it.
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
from app.shared.dates import user_today

#: How far ahead occurrences are written. Wide enough to fill the calendar's
#: month view and the task page's fortnight, so neither has to ask for more;
#: narrow enough that a daily chore is sixty rows rather than a standing
#: commitment to fill the table forever.
MATERIALISE_AHEAD_DAYS = 60

#: How far back a first run will reach. A repeating chore missed three months ago
#: is not work to do, it is noise -- unlike a missed payment, which really is
#: owed. So this is much shorter than the payment catch-up.
MATERIALISE_BEHIND_DAYS = 14


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
    """Return the user's course ids mapped to their codes.

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


def skipped_of(rule: RecurringTaskModel) -> list[date]:
    """Return a rule's cancelled dates, parsed from their stored ISO strings.

    Args:
        rule: The repeating task.

    Returns:
        Its skipped dates as `date` objects; empty when none.
    """
    return [parse_date(value) for value in (rule.skipped_dates or [])]


def written_dates(db: Session, recurring_id: uuid.UUID) -> set[date]:
    """Return the occurrence dates this rule has already written a task for.

    Keyed on `occurrence_date`, never `due_date`, so an occurrence the student moved
    still counts as written for the date the rule produced it.

    Args:
        db: Open database session.
        recurring_id: The rule.

    Returns:
        The set of occurrence dates; empty when none is written.
    """
    rows = (
        db.query(TaskModel.occurrence_date)
        .filter(TaskModel.recurring_id == recurring_id)
        .distinct()
        .all()
    )
    return {row.occurrence_date for row in rows}


def attach_rule(db: Session, rule: RecurringTaskModel, codes: dict[uuid.UUID, str] | None = None):
    """Set the derived fields the response expects on a rule row.

    Attaches `recurrence`, `course_code` and `next_due_on` to the instance only.

    Args:
        db: Open database session.
        rule: The rule row.
        codes: Course ids mapped to codes; None looks them up.

    Returns:
        The same row.
    """
    rule.recurrence = recurrence_of(rule)
    rule.course_code = (codes or course_codes(db, rule.user_id)).get(rule.course_id)
    rule.next_due_on = next_due(db, rule)
    return rule


def next_due(db: Session, rule: RecurringTaskModel) -> date | None:
    """Return the rule's first occurrence from the owner's today that is not yet done.

    Looks 60 days ahead. Done occurrences are matched by their current `due_date`,
    not `occurrence_date`, so a moved occurrence can be reported as still due.

    Args:
        db: Open database session.
        rule: The rule row.

    Returns:
        The date; None when nothing outstanding falls in the next 60 days.
    """
    # The rule carries its owner, so the horizon is that student's today.
    horizon = user_today(db, rule.user_id)
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
    """Return the user's repeating tasks, by start date.

    Args:
        db: Open database session.
        user_id: Whose rules.
        include_inactive: Also return paused rules.

    Returns:
        The rule rows with derived fields attached; None when the user does not
        exist.
    """
    if not user_exists(db, user_id):
        return None

    query = db.query(RecurringTaskModel).filter(RecurringTaskModel.user_id == user_id)
    if not include_inactive:
        query = query.filter(RecurringTaskModel.active.is_(True))

    rules = query.order_by(RecurringTaskModel.starts_on).all()
    codes = course_codes(db, user_id)
    return [attach_rule(db, rule, codes) for rule in rules]


def get_rule(db: Session, user_id: uuid.UUID, rule_id: uuid.UUID):
    """Return one of the user's repeating tasks with derived fields, or None.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        rule_id: The repeating task to fetch.

    Returns:
        The rule with its derived fields attached, or None when it is missing or another
        user's.
    """
    rule = (
        db.query(RecurringTaskModel)
        .filter(RecurringTaskModel.id == rule_id, RecurringTaskModel.user_id == user_id)
        .first()
    )
    return None if rule is None else attach_rule(db, rule)


def create_rule(db: Session, user_id: uuid.UUID, data: RecurringTaskCreate):
    """Create a repeating task and write its occurrences for the window at once.

    Commits twice: the rule, then the occurrences.

    Args:
        db: Open database session.
        user_id: Whose rule.
        data: The rule and its template; the title is stripped.

    Returns:
        The new rule row with derived fields; None when the user does not exist.

    Raises:
        ValueError: If `course_id` is not one of the user's courses.
    """
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
        priority=data.priority,
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
    """Change the fields sent on a repeating task and bring its occurrences in line.

    Commits the rule, then resyncs outstanding occurrences and writes any new dates
    from today on (never back-filling), and commits again.

    Args:
        db: Open database session.
        user_id: Whose rule.
        rule_id: The rule.
        data: The fields to change; a null `recurrence` keeps the rule.

    Returns:
        The updated rule row with derived fields; None when it is not the user's.

    Raises:
        ValueError: If a new `course_id` is not one of the user's courses, or the
            repeat would end before it starts.
    """
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

    db.commit()
    db.refresh(rule)
    resync_occurrences(db, rule)
    materialise(db, user_id, rule, since=user_today(db, user_id))
    db.commit()
    db.refresh(rule)
    return attach_rule(db, rule)


def resync_occurrences(db: Session, rule: RecurringTaskModel) -> None:
    """Bring a rule's outstanding occurrences back in line with its current template.

    Every outstanding occurrence, overdue ones included, takes the rule's title,
    notes, time, estimate, course, priority and tags; outstanding ones from today to
    the window's end whose date the rule no longer produces are deleted. Ticked-off
    occurrences are never touched. Flushes only.

    Args:
        db: Open database session.
        rule: The rule row, already updated.

    Note:
        Nothing marks a hand-edited occurrence, so an edit to a future one is
        overwritten here; that is deliberate.
    """
    horizon = user_today(db, rule.user_id)
    window_end = horizon + timedelta(days=MATERIALISE_AHEAD_DAYS)
    wanted = set(
        occurrences(
            rule_of(rule),
            rule.starts_on,
            max(rule.starts_on, horizon - timedelta(days=MATERIALISE_BEHIND_DAYS)),
            window_end,
            skipped_of(rule),
        )
    )

    # Dropped first, so the update below does not bother with rows on their way
    # out. Bounded by the same window the rule writes into, so an occurrence
    # beyond it is left alone rather than deleted for being unrecognised.
    #
    # On `occurrence_date` throughout, for the same reason `written_dates` is:
    # the question is "does the rule still call for this occurrence", and an
    # occurrence the student has dragged to another day is still the one the
    # rule made. Matching on due_date deleted exactly the ones that had been
    # moved -- the edits, and nothing else.
    stale = (
        db.query(TaskModel)
        .filter(
            TaskModel.recurring_id == rule.id,
            TaskModel.done.is_(False),
            TaskModel.occurrence_date >= horizon,
            TaskModel.occurrence_date <= window_end,
        )
        .all()
    )
    for task in stale:
        if task.occurrence_date not in wanted:
            db.delete(task)

    outstanding = (
        db.query(TaskModel)
        .filter(TaskModel.recurring_id == rule.id, TaskModel.done.is_(False))
        .all()
    )
    for task in outstanding:
        task.title = rule.title
        task.notes = rule.notes
        task.due_time = rule.due_time
        task.estimated_minutes = rule.estimated_minutes
        task.course_id = rule.course_id
        task.priority = rule.priority
        # Rewritten whole rather than mutated: SQLAlchemy does not track a change
        # made inside a JSON column.
        task.tags = list(rule.tags or [])

    db.flush()


def delete_rule(db: Session, user_id: uuid.UUID, rule_id: uuid.UUID, drop_pending: bool = True):
    """Delete a repeating task, keeping the occurrences already ticked off.

    Kept occurrences lose their link to the rule. Commits.

    Args:
        db: Open database session.
        user_id: Whose rule.
        rule_id: The rule.
        drop_pending: Also delete the outstanding occurrences (the default).

    Returns:
        A copy of the deleted rule; None when it is not the user's.
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
    """Cancel one occurrence of a repeating task.

    Adds the date to `skipped_dates` and deletes any outstanding task whose
    `due_date` is that day (matched on `due_date`, not `occurrence_date`). Commits.

    Args:
        db: Open database session.
        user_id: Whose rule.
        rule_id: The rule.
        on_date: The date to cancel.

    Returns:
        The rule row with derived fields; None when it is not the user's.
    """
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

def materialise(
    db: Session,
    user_id: uuid.UUID,
    rule: RecurringTaskModel,
    *,
    since: date | None = None,
) -> list[TaskModel]:
    """Write a rule's missing occurrences for the rolling window. Flushes only.

    The window runs from 14 days back (never before `starts_on`) to 60 days ahead of
    the owner's today. A paused rule writes nothing.

    Args:
        db: Open database session.
        user_id: The rule's owner.
        rule: The rule row.
        since: Raise the window's start to this date; an edit passes today so a
            changed rule never back-fills overdue work that was never assigned.

    Returns:
        The task rows written; empty when nothing was missing.
    """
    if not rule.active:
        return []

    horizon = user_today(db, user_id)
    window_start = max(rule.starts_on, horizon - timedelta(days=MATERIALISE_BEHIND_DAYS))
    if since is not None:
        window_start = max(window_start, since)
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
            # Where it sits, and separately what it is. They start equal and
            # only `due_date` ever moves.
            occurrence_date=on_date,
            due_time=rule.due_time,
            estimated_minutes=rule.estimated_minutes,
            tags=list(rule.tags or []),
            priority=rule.priority,
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
    """Write the missing occurrences of every active repeating task the user has.

    Idempotent, so the Tasks page calls it on every load. Commits when it writes
    anything.

    Args:
        db: Open database session.
        user_id: Whose rules.

    Returns:
        How many occurrences were written and the rows themselves; None when the
        user does not exist.
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
