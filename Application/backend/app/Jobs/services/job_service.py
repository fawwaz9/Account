"""Service functions for jobs, their shifts, and what was recorded about each shift.

A shift is a calendar event with a `job_id` and, for a pattern, a weekly rule, so
the recurrence engine, free time, the week's load and blackout scoping all
handle it with no code of their own. What happened on one date of a shift is a
`shift_records` row keyed by (event_id, on_date). A confirmed cash tip is filed
as one income row in the account chosen for cash tips, or held when none is.
"""

import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app._database.models import (
    AccountModel,
    EventModel,
    JobModel,
    ShiftRecordModel,
    TransactionModel,
    UserModel,
)
from app.Finances.schemas.transaction import TransactionKind
from app.Calendar.schemas.event import EventKind
from app.Calendar.services.event_service import list_occurrences
from app.Jobs.services.pay_schedule import apply_pay_days, pattern_of, pay_dates, pay_days_of
from app.Calendar.utils.recurrence import WEEKLY, format_byday
from app.Calendar.utils.rule_columns import apply_recurrence, recurrence_of
from app.Jobs.schemas.job import (
    Job,
    ShiftCreate,
    JobCreate,
    JobKind,
    JobUpdate,
    ShiftOccurrence,
    ShiftRecord,
    ShiftRecordUpsert,
    ShiftScheduleCreate,
)
from app.Tasks.services.task_service import user_exists
from app.shared.dates import user_today

SHIFT = EventKind.SHIFT.value
INCOME = TransactionKind.INCOME.value

#: How far ahead the next pay date is looked for. A rule that produces nothing
#: inside a year has effectively stopped, and walking further is a spin.
PAY_LOOKAHEAD_DAYS = 366


def minutes_between(start: time, end: time) -> int:
    """Return the whole minutes from one clock time to a later one on the same day.

    Never negative: an end at or before the start gives 0.

    Args:
        start: Clock time the shift starts.
        end: Clock time the shift ends.

    Returns:
        Minutes from `start` to `end`, at least 0.
    """
    started = start.hour * 60 + start.minute
    ended = end.hour * 60 + end.minute
    return max(0, ended - started)


def owned_job(db: Session, user_id: uuid.UUID, job_id: uuid.UUID) -> JobModel | None:
    """Return the user's job with this id, or None.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        job_id: The job to fetch.

    Returns:
        The job row, or None when it is missing or another user's.
    """
    return (
        db.query(JobModel)
        .filter(JobModel.id == job_id, JobModel.user_id == user_id)
        .first()
    )


def next_pay_on(job: JobModel, on_day: date) -> date | None:
    """Return the next date a job pays, on or after a day.

    Read from the schedule (`pay_schedule.pay_dates`), looking up to
    `PAY_LOOKAHEAD_DAYS` ahead; a set date moved off a weekend reads as the day it
    is actually paid.

    Args:
        job: The job row.
        on_day: The day to look from, inclusive.

    Returns:
        The date; None without a schedule, or when the schedule produces nothing
        within a year.
    """
    ahead = pay_dates(job, on_day, on_day + timedelta(days=PAY_LOOKAHEAD_DAYS))
    return ahead[0] if ahead else None


def as_schema(job: JobModel, on_day: date) -> Job:
    """Build a job's response, with its next pay date as of a day.

    Args:
        job: The job row.
        on_day: The user's today.

    Returns:
        The job; `pay_schedule` is None when it pays on set days of the month.
    """
    return Job(
        id=job.id,
        name=job.name,
        employer=job.employer,
        kind=JobKind(job.kind),
        hourly_rate=job.hourly_rate,
        period_amount=job.period_amount,
        started_on=job.started_on,
        ended_on=job.ended_on,
        pay_starts_on=job.pay_starts_on,
        # One or the other: a days-of-the-month job also reads "monthly" on the
        # rule columns, which is not a schedule of its own.
        pay_schedule=None if pattern_of(job) else recurrence_of(job),
        pay_days=pay_days_of(job),
        archived=job.archived,
        position=job.position,
        created_at=job.created_at,
        next_pay_on=next_pay_on(job, on_day),
        is_current=job.ended_on is None,
    )


def list_jobs(db: Session, user_id: uuid.UUID, include_archived: bool = False):
    """Return the user's jobs: current ones first, then by the user's order and name.

    Args:
        db: Open database session.
        user_id: Whose jobs.
        include_archived: Also return archived jobs.

    Returns:
        The jobs; None when the user does not exist.
    """
    if not user_exists(db, user_id):
        return None

    query = db.query(JobModel).filter(JobModel.user_id == user_id)
    if not include_archived:
        query = query.filter(JobModel.archived.is_(False))

    jobs = query.all()
    # Current jobs first, then by the order the student put them in: a job you
    # have left is history and should not sit above one you turn up to.
    jobs.sort(key=lambda job: (job.ended_on is not None, job.position, job.name))
    # Resolved once, not per row: this is a primary-key lookup and a
    # comprehension over it would be an N+1.
    on_day = user_today(db, user_id)
    return [as_schema(job, on_day) for job in jobs]


def get_job(db: Session, user_id: uuid.UUID, job_id: uuid.UUID):
    """Return one of the user's jobs, or None when it is not theirs.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        job_id: The job to fetch.

    Returns:
        The job as its API schema, or None when it is missing or another user's.
    """
    job = owned_job(db, user_id, job_id)
    return None if job is None else as_schema(job, user_today(db, user_id))


def create_job(db: Session, user_id: uuid.UUID, data: JobCreate):
    """Create a job for the user, placed last in their order.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose job.
        data: The job and its pay schedule; the name is stripped.

    Returns:
        The new job; None when the user does not exist.
    """
    if not user_exists(db, user_id):
        return None

    highest = (
        db.query(JobModel)
        .filter(JobModel.user_id == user_id)
        .order_by(JobModel.position.desc())
        .first()
    )

    job = JobModel(
        id=uuid.uuid4(),
        user_id=user_id,
        name=data.name.strip(),
        employer=data.employer,
        kind=data.kind.value,
        hourly_rate=data.hourly_rate,
        period_amount=data.period_amount,
        started_on=data.started_on,
        ended_on=data.ended_on,
        pay_starts_on=data.pay_starts_on,
        archived=data.archived,
        position=(highest.position + 1) if highest else 0,
    )
    apply_recurrence(job, data.pay_schedule)
    apply_pay_days(job, data.pay_days)

    db.add(job)
    db.commit()
    db.refresh(job)
    return as_schema(job, user_today(db, user_id))


def check_pay_fields(job: JobModel) -> None:
    """Apply the create-time pay rules to a job after an edit, clearing unused fields.

    An hourly job keeps only its rate, a salaried one only its period amount, and a
    contract job neither. Only changes the row.

    Args:
        job: The job row, already patched.

    Raises:
        ValueError: If an hourly job has no rate or a salaried job no period
            amount.
    """
    if job.kind == JobKind.HOURLY.value:
        if job.hourly_rate is None:
            raise ValueError("An hourly job needs an hourly rate")
        job.period_amount = None
    elif job.kind == JobKind.SALARIED.value:
        if job.period_amount is None:
            raise ValueError("A salaried job needs an amount per pay period")
        job.hourly_rate = None
    else:
        job.hourly_rate = None
        job.period_amount = None


def update_job(db: Session, user_id: uuid.UUID, job_id: uuid.UUID, data: JobUpdate):
    """Change the fields sent on one of the user's jobs.

    A pay schedule or set days left out of the patch keep what is stored, and an
    explicit null clears it; the pay fields are then checked against the kind.
    Commits.

    Args:
        db: Open database session.
        user_id: Whose job.
        job_id: The job.
        data: The fields to change.

    Returns:
        The updated job; None when it is not the user's.

    Raises:
        ValueError: If both kinds of pay schedule would be set, the job would end
            before it starts, or the kind's pay field is missing.
    """
    job = owned_job(db, user_id, job_id)
    if job is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    touches_schedule = "pay_schedule" in update_data or "pay_days" in update_data
    update_data.pop("pay_schedule", None)
    update_data.pop("pay_days", None)
    if "kind" in update_data and update_data["kind"] is not None:
        update_data["kind"] = JobKind(update_data["kind"]).value

    for key, value in update_data.items():
        setattr(job, key, value)

    if touches_schedule:
        # Whichever half the patch leaves out keeps what is stored, and an
        # explicit null clears. It used to skip a null pay_schedule, so
        # choosing "doesn't repeat" never stopped a schedule once set.
        fields = data.model_fields_set
        pattern = data.pay_days if "pay_days" in fields else pay_days_of(job)
        rule = data.pay_schedule if "pay_schedule" in fields else (
            None if pattern_of(job) else recurrence_of(job)
        )
        if rule is not None and pattern is not None:
            raise ValueError("Pay by a repeat or by days of the month, not both")
        apply_recurrence(job, rule)
        apply_pay_days(job, pattern)


    if job.ended_on and job.started_on and job.ended_on < job.started_on:
        raise ValueError("A job cannot end before it starts")

    check_pay_fields(job)

    db.commit()
    db.refresh(job)
    return as_schema(job, user_today(db, user_id))


def delete_job(db: Session, user_id: uuid.UUID, job_id: uuid.UUID):
    """Delete a job, its shifts, their records and its paycheques.

    Meant for a job entered by mistake; ending or archiving keeps the history.
    Ledger rows already written (cash tips, cheque deposits) stay. Shift records
    are deleted before the shift events, which a bulk delete removes. Commits.

    Args:
        db: Open database session.
        user_id: Whose job.
        job_id: The job.

    Returns:
        A copy of the deleted job; None when it is not the user's.
    """
    job = owned_job(db, user_id, job_id)
    if job is None:
        return None

    removed = as_schema(job, user_today(db, user_id))

    # In this order, because each points at the next. A shift record points at
    # its calendar block, so the records go before the blocks: the blocks are a
    # bulk delete, which skips the ORM's cascades, and with a confirmed shift
    # still pointing at one the delete failed the foreign key and every job
    # with a single confirmed shift could not be removed at all. Then the job,
    # whose cascade takes its paycheques. Ledger transactions stay, as the
    # dialog promises -- a cash tip already filed is money that arrived.
    db.query(ShiftRecordModel).filter(
        ShiftRecordModel.user_id == user_id, ShiftRecordModel.job_id == job_id
    ).delete(synchronize_session=False)
    db.query(EventModel).filter(
        EventModel.user_id == user_id, EventModel.job_id == job_id
    ).delete(synchronize_session=False)
    db.delete(job)
    db.commit()
    return removed


def shift_window(job: JobModel, data: ShiftScheduleCreate) -> tuple[date, date]:
    """Return the dates a shift pattern runs, preferring the form's over the job's.

    Args:
        job: The job row, whose start and end dates are the fallback.
        data: The pattern form.

    Returns:
        The first date and the last date, which may be None for an open-ended
        pattern.

    Raises:
        ValueError: If no start date is given or stored, or the pattern ends
            before it starts.
    """
    starts_on = data.starts_on or job.started_on
    ends_on = data.ends_on or job.ended_on

    if starts_on is None:
        raise ValueError("This job has no start date, so give the dates here")
    if ends_on is not None and ends_on < starts_on:
        raise ValueError("A schedule cannot end before it starts")

    return starts_on, ends_on


def set_shift_schedule(
    db: Session, user_id: uuid.UUID, job_id: uuid.UUID, data: ShiftScheduleCreate
):
    """Replace a job's weekly shift pattern with the blocks given.

    Deletes the job's repeating shift events (one-off shifts are kept) and writes a
    weekly event per block. Commits.

    Args:
        db: Open database session.
        user_id: Whose job.
        job_id: The job.
        data: The weekly blocks and, optionally, the dates.

    Returns:
        The new events' ids; None when the job is not the user's.

    Raises:
        ValueError: If the dates are missing or inverted.

    Note:
        The old events are deleted directly; a confirmed shift record still
        pointing at one makes the delete fail its foreign key.
    """
    job = owned_job(db, user_id, job_id)
    if job is None:
        return None

    starts_on, ends_on = shift_window(job, data)

    existing = (
        db.query(EventModel)
        .filter(
            EventModel.user_id == user_id,
            EventModel.job_id == job_id,
            EventModel.kind == SHIFT,
            # Only the pattern. A one-off shift was entered by hand for a date
            # that actually happened, and saving a new weekly pattern must not
            # quietly delete a fortnight of them.
            EventModel.recur_freq.isnot(None),
        )
        .all()
    )
    for event in existing:
        db.delete(event)
    db.flush()

    created: list[EventModel] = []
    for meeting in data.meetings:
        event = EventModel(
            id=uuid.uuid4(),
            user_id=user_id,
            course_id=None,
            job_id=job_id,
            title=job.name,
            kind=SHIFT,
            location=meeting.location,
            starts_on=starts_on,
            start_time=meeting.start_time,
            end_time=meeting.end_time,
            recur_freq=WEEKLY,
            recur_interval=1,
            recur_byday=format_byday(meeting.days),
            recur_until=ends_on,
            recur_count=None,
            skipped_dates=[],
        )
        db.add(event)
        created.append(event)

    db.commit()
    return [event.id for event in created]


def add_shift(db: Session, user_id: uuid.UUID, job_id: uuid.UUID, data: ShiftCreate):
    """Add one shift on one date for a job, as an event with no repeat rule.

    Commits.

    Args:
        db: Open database session.
        user_id: Whose job.
        job_id: The job.
        data: The date, times and location.

    Returns:
        The new event's id; None when the job is not the user's.
    """
    job = owned_job(db, user_id, job_id)
    if job is None:
        return None

    event = EventModel(
        id=uuid.uuid4(),
        user_id=user_id,
        course_id=None,
        job_id=job_id,
        title=job.name,
        kind=SHIFT,
        location=data.location,
        starts_on=data.on_date,
        start_time=data.start_time,
        end_time=data.end_time,
        recur_freq=None,
        recur_interval=1,
        recur_byday=None,
        recur_until=None,
        recur_count=None,
        skipped_dates=[],
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event.id


def remove_shift(db: Session, user_id: uuid.UUID, event_id: uuid.UUID):
    """Delete a one-off shift and everything recorded about it.

    Any cash tip it filed is removed from the ledger too (every row of an older
    split tip's group). Commits.

    Args:
        db: Open database session.
        user_id: Whose shift.
        event_id: The shift event.

    Returns:
        The event id; None when it is not one of the user's shifts.

    Raises:
        ValueError: If the shift comes from a repeating pattern, whose dates are
            cancelled by skipping instead.
    """
    event = (
        db.query(EventModel)
        .filter(
            EventModel.id == event_id,
            EventModel.user_id == user_id,
            EventModel.kind == SHIFT,
        )
        .first()
    )
    if event is None:
        return None
    if event.recur_freq is not None:
        raise ValueError("That shift comes from a repeating pattern")

    # A cash tip is several ledger rows tied by a group, and the record only
    # points at one of them -- the same shape `sync_cash_tip` already has to
    # unpick. A bulk delete of the record alone would leave that money in the
    # ledger explaining nothing, the same fault an orphaned tuition payment or
    # paycheque was made of.
    records = (
        db.query(ShiftRecordModel)
        .filter(ShiftRecordModel.event_id == event_id)
        .all()
    )

    # Worked out before anything is deleted, and acted on after the records are
    # gone. `shift_records.tip_transaction_id` is a foreign key, so removing the
    # ledger row while a record still points at it is a constraint violation,
    # not merely untidy ordering -- which is exactly what enforcing foreign keys
    # turned from a silent dangling pointer into a visible error.
    tip_groups: list[uuid.UUID] = []
    tip_rows: list[uuid.UUID] = []
    for record in records:
        if record.tip_transaction_id is None:
            continue

        anchor = (
            db.query(TransactionModel)
            .filter(
                TransactionModel.id == record.tip_transaction_id,
                TransactionModel.user_id == user_id,
            )
            .first()
        )
        if anchor is None:
            continue

        if anchor.group_id is not None:
            tip_groups.append(anchor.group_id)
        else:
            tip_rows.append(anchor.id)

    for record in records:
        db.delete(record)
    db.delete(event)
    db.flush()

    for group_id in tip_groups:
        db.query(TransactionModel).filter(
            TransactionModel.user_id == user_id,
            TransactionModel.group_id == group_id,
        ).delete(synchronize_session=False)

    for row_id in tip_rows:
        db.query(TransactionModel).filter(
            TransactionModel.user_id == user_id,
            TransactionModel.id == row_id,
        ).delete(synchronize_session=False)

    db.commit()
    return event_id


def records_by_date(
    db: Session, user_id: uuid.UUID, start: date, end: date
) -> dict[tuple[uuid.UUID, date], ShiftRecordModel]:
    """Return the user's shift records in a window, keyed by (event_id, on_date).

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        start: First day of the window, inclusive.
        end: Last day of the window, inclusive.

    Returns:
        Shift record by (event id, date); dates with no record are absent.
    """
    rows = (
        db.query(ShiftRecordModel)
        .filter(
            ShiftRecordModel.user_id == user_id,
            ShiftRecordModel.on_date >= start,
            ShiftRecordModel.on_date <= end,
        )
        .all()
    )
    return {(row.event_id, row.on_date): row for row in rows}


def list_shifts(
    db: Session,
    user_id: uuid.UUID,
    start: date,
    end: date,
    on_day: date | None = None,
) -> list[ShiftOccurrence] | None:
    """Return every shift date in a window, with what is known about each.

    Expanded by the calendar's own `list_occurrences`, so it agrees with what the
    calendar draws. A shift on or before `on_day` that is unconfirmed counts at its
    scheduled hours and is flagged `assumed`.

    Args:
        db: Open database session.
        user_id: Whose shifts.
        start: First date, inclusive.
        end: Last date, inclusive.
        on_day: The day that decides which shifts are past; defaults to the
            user's today.

    Returns:
        The shifts by date and start time; None when the user does not exist.

    Raises:
        ValueError: If the window is inverted or longer than the calendar allows.
    """
    expanded = list_occurrences(db, user_id, start, end)
    if expanded is None:
        return None

    jobs = {job.id: job for job in db.query(JobModel).filter(JobModel.user_id == user_id)}
    records = records_by_date(db, user_id, start, end)
    anchor = on_day or user_today(db, user_id)

    shifts: list[ShiftOccurrence] = []
    for item in expanded:
        if item.kind != SHIFT or item.job_id is None:
            continue

        job = jobs.get(item.job_id)
        if job is None:
            continue

        scheduled = 0
        if item.start_time and item.end_time:
            scheduled = minutes_between(item.start_time, item.end_time)

        record = records.get((item.event_id, item.on_date))
        counted = scheduled
        if record and record.worked_start and record.worked_end:
            counted = minutes_between(record.worked_start, record.worked_end)

        confirmed = bool(record and record.confirmed)
        shifts.append(ShiftOccurrence(
            event_id=item.event_id,
            job_id=job.id,
            job_name=job.name,
            on_date=item.on_date,
            title=item.title,
            scheduled_start=item.start_time,
            scheduled_end=item.end_time,
            location=item.location,
            scheduled_minutes=scheduled,
            worked_start=record.worked_start if record else None,
            worked_end=record.worked_end if record else None,
            counted_minutes=counted,
            confirmed=confirmed,
            repeats=item.repeats,
            # A past shift nobody confirmed still counts, at the hours it was
            # scheduled for, and says so. Dropping it would make a fortnight
            # nobody did the admin for read as a fortnight nobody worked.
            assumed=item.on_date <= anchor and not confirmed,
            tip_amount=record.tip_amount if record else 0.0,
            tip_is_cash=record.tip_is_cash if record else True,
            tip_in_ledger=bool(record and record.tip_transaction_id is not None),
            rate_override=record.rate_override if record else None,
            notes=record.notes if record else None,
        ))

    shifts.sort(key=lambda shift: (shift.on_date, shift.scheduled_start or time.min))
    return shifts


def confirm_shift(
    db: Session,
    user_id: uuid.UUID,
    event_id: uuid.UUID,
    on_date: date,
    data: ShiftRecordUpsert,
):
    """Record what happened on one date of a shift, creating or replacing its record.

    The record is keyed by (event_id, on_date), so recording the same date twice
    updates one row. A changed cash tip is re-filed in the ledger. Commits.

    Args:
        db: Open database session.
        user_id: Whose shift.
        event_id: The shift event.
        on_date: The date of the occurrence.
        data: Worked times, confirmation, tip, rate override and notes.

    Returns:
        The record; None when the event is not one of the user's shifts.
    """
    event = (
        db.query(EventModel)
        .filter(
            EventModel.id == event_id,
            EventModel.user_id == user_id,
            EventModel.kind == SHIFT,
        )
        .first()
    )
    if event is None or event.job_id is None:
        return None

    record = (
        db.query(ShiftRecordModel)
        .filter(
            ShiftRecordModel.event_id == event_id,
            ShiftRecordModel.on_date == on_date,
            ShiftRecordModel.user_id == user_id,
        )
        .first()
    )
    if record is None:
        record = ShiftRecordModel(
            id=uuid.uuid4(),
            user_id=user_id,
            event_id=event_id,
            job_id=event.job_id,
            on_date=on_date,
        )
        db.add(record)

    # The tip as it was, so sync_cash_tip can tell a re-save of the hours from a
    # change to the tip. A new record had no tip.
    previous_tip = (
        record.tip_amount or 0.0,
        True if record.tip_is_cash is None else record.tip_is_cash,
    )

    record.worked_start = data.worked_start
    record.worked_end = data.worked_end
    record.confirmed = data.confirmed
    record.tip_amount = data.tip_amount
    record.tip_is_cash = data.tip_is_cash
    record.rate_override = data.rate_override
    record.notes = data.notes

    sync_cash_tip(db, user_id, record, previous_tip)

    db.commit()
    db.refresh(record)
    return ShiftRecord.model_validate(record)


def cash_tip_account(db: Session, user_id: uuid.UUID) -> AccountModel | None:
    """Return the active account cash tips are filed into, or None when there is none.

    None covers no choice, a stored id that does not parse, and a chosen account that
    is archived or gone; callers hold the tip in every case.

    Args:
        db: Open database session.
        user_id: Owner of the rows.

    Returns:
        The chosen account if it exists and is not archived, else None.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    raw = (user.preferences or {}).get("cash_tip_account_id") if user else None
    if not raw:
        return None
    try:
        account_id = uuid.UUID(str(raw))
    except ValueError:
        return None
    return (
        db.query(AccountModel)
        .filter(
            AccountModel.id == account_id,
            AccountModel.user_id == user_id,
            AccountModel.archived.is_(False),
        )
        .first()
    )


def file_cash_tip(
    db: Session, user_id: uuid.UUID, record: ShiftRecordModel, account: AccountModel
) -> TransactionModel:
    """Write one income row for a shift's cash tip and point the record at it.

    One row in one account, never split by income share. Flushes only.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        record: The shift record holding the tip.
        account: The account to file it in.

    Returns:
        The new income row.
    """
    job = db.query(JobModel).filter(JobModel.id == record.job_id).first()
    row = TransactionModel(
        id=uuid.uuid4(),
        user_id=user_id,
        account_id=account.id,
        kind=INCOME,
        amount=round(record.tip_amount, 2),
        description=f"{job.name if job else 'Shift'} tips",
        occurred_on=record.on_date,
    )
    db.add(row)
    db.flush()
    record.tip_transaction_id = row.id
    db.flush()
    return row


def sync_cash_tip(
    db: Session,
    user_id: uuid.UUID,
    record: ShiftRecordModel,
    previous_tip: tuple[float, bool],
) -> None:
    """Keep a shift record's cash tip and its ledger row in step.

    A tip already filed and unchanged is left where it landed. Otherwise any rows the
    old tip wrote are deleted and, for a cash tip above 0, a new one is filed, or
    held when no cash-tip account is available. On-cheque tips never write a row.
    Flushes only.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        record: The shift record, already updated.
        previous_tip: The record's (amount, is_cash) before the update.
    """
    wants_row = record.tip_amount > 0 and record.tip_is_cash
    unchanged = (round(previous_tip[0], 2), previous_tip[1]) == (
        round(record.tip_amount, 2), record.tip_is_cash
    )

    # Tips from now on: a tip already in the budget is never moved by re-saving
    # the shift for its hours or its notes -- including a tip from before this
    # rule, which was split across several accounts. Only a changed tip, or one
    # that never reached the budget, is (re)written.
    if unchanged and record.tip_transaction_id is not None:
        return

    # A tip written by the old rule is several rows tied by a group; the record
    # points at one, and the group finds the rest. Deleting only the row it
    # points at would orphan the others.
    existing = []
    if record.tip_transaction_id is not None:
        anchor = (
            db.query(TransactionModel)
            .filter(
                TransactionModel.id == record.tip_transaction_id,
                TransactionModel.user_id == user_id,
            )
            .first()
        )
        if anchor is not None:
            existing = (
                db.query(TransactionModel)
                .filter(
                    TransactionModel.user_id == user_id,
                    TransactionModel.group_id == anchor.group_id,
                )
                .all()
                if anchor.group_id is not None
                else [anchor]
            )

    # Rewritten rather than patched: the amount changed, so the row changed.
    for row in existing:
        db.delete(row)
    record.tip_transaction_id = None
    db.flush()

    if not wants_row:
        return

    account = cash_tip_account(db, user_id)
    if account is None:
        # Held. Recording the shift still succeeds -- refusing would block
        # logging your hours over an unrelated setting.
        return

    file_cash_tip(db, user_id, record, account)


def set_cash_tip_account(
    db: Session, user_id: uuid.UUID, account_id: uuid.UUID | None
) -> int | None:
    """Choose where cash tips go, and file every held tip into it.

    Saved in the user's preferences. Tips already in the ledger stay where they
    landed; clearing the choice files nothing and holds later tips. Commits.

    Args:
        db: Open database session.
        user_id: Whose setting.
        account_id: One of the user's active accounts; None clears the choice.

    Returns:
        How many held tips were filed; None when the user does not exist or the
        account is not one of the user's active accounts, in which case nothing
        is written.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None

    account = None
    if account_id is not None:
        account = (
            db.query(AccountModel)
            .filter(
                AccountModel.id == account_id,
                AccountModel.user_id == user_id,
                AccountModel.archived.is_(False),
            )
            .first()
        )
        if account is None:
            return None

    # Reassigned whole: SQLAlchemy does not see a mutation inside a JSON column.
    user.preferences = {
        **(user.preferences or {}),
        "cash_tip_account_id": str(account_id) if account_id is not None else None,
    }
    db.flush()

    filed = 0
    if account is not None:
        held = (
            db.query(ShiftRecordModel)
            .filter(
                ShiftRecordModel.user_id == user_id,
                ShiftRecordModel.tip_is_cash.is_(True),
                ShiftRecordModel.tip_amount > 0,
                ShiftRecordModel.tip_transaction_id.is_(None),
            )
            .all()
        )
        for record in held:
            file_cash_tip(db, user_id, record, account)
            filed += 1

    db.commit()
    return filed
