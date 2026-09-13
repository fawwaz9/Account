"""Jobs, and the shifts they are worked in.

A shift is an event with a `job_id` and a rule, exactly as a lecture is an event
with a `course_id` and a rule. That is not a shortcut: a shift genuinely is a
block of time on a clock, and giving it a table of its own would mean teaching
the calendar, the free-block finder and the week-load figure about a second kind
of timed thing -- the way tasks already have to be merged in separately.

Making it an event buys four behaviours with no code at all:

* the recurrence engine expands "every Tuesday and Thursday" on read,
* `free_blocks` already subtracts any timed occurrence, so work reduces study
  time without knowing what work is,
* `crunch` scores an unrecognised kind zero, so a shift is correctly absent from
  a radar that measures academic pressure rather than commitment,
* term blackouts skip only course-linked events, so a reading break already
  cannot cancel a shift you are still expected to turn up for.

What an event cannot hold is what actually happened on one of those dates, since
a repeating shift is one row expanded on read and there is nothing anywhere that
represents "this Friday". That is what `shift_records` is for, keyed by
`(event_id, on_date)`.
"""

import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app._database.models import (
    EventModel,
    JobModel,
    ShiftRecordModel,
    TransactionModel,
)
from app.Finances.schemas.transaction import TransactionKind
from app.Finances.services.deposit_service import active_accounts, split_income
from app.Calendar.schemas.event import EventKind
from app.Calendar.services.event_service import list_occurrences
from app.Calendar.utils.recurrence import (
    WEEKLY,
    Rule,
    format_byday,
    occurrences,
    parse_byday,
)
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

SHIFT = EventKind.SHIFT.value
INCOME = TransactionKind.INCOME.value

#: How far ahead the next pay date is looked for. A rule that produces nothing
#: inside a year has effectively stopped, and walking further is a spin.
PAY_LOOKAHEAD_DAYS = 366


def today() -> date:
    return date.today()


def minutes_between(start: time, end: time) -> int:
    """Whole minutes from one clock time to another on the same day."""
    started = start.hour * 60 + start.minute
    ended = end.hour * 60 + end.minute
    return max(0, ended - started)


def owned_job(db: Session, user_id: uuid.UUID, job_id: uuid.UUID) -> JobModel | None:
    return (
        db.query(JobModel)
        .filter(JobModel.id == job_id, JobModel.user_id == user_id)
        .first()
    )


def next_pay_on(job: JobModel, on_day: date | None = None) -> date | None:
    """The next date this job's pay rule produces, or None without a rule.

    Read from the rule rather than stored, like every other repeat in the app.
    Nothing is ever materialised from it: a cheque exists because one arrived
    and was entered, never because a date came round.
    """
    if job.pay_starts_on is None or not job.recur_freq:
        return None

    anchor = on_day or today()
    rule = Rule(
        freq=job.recur_freq,
        interval=job.recur_interval or 1,
        byday=parse_byday(job.recur_byday),
        until=job.recur_until,
        count=job.recur_count,
    )
    ahead = occurrences(
        rule, job.pay_starts_on, anchor, anchor + timedelta(days=PAY_LOOKAHEAD_DAYS)
    )
    return ahead[0] if ahead else None


def as_schema(job: JobModel, on_day: date | None = None) -> Job:
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
        pay_schedule=recurrence_of(job),
        archived=job.archived,
        position=job.position,
        created_at=job.created_at,
        next_pay_on=next_pay_on(job, on_day),
        is_current=job.ended_on is None,
    )


def list_jobs(db: Session, user_id: uuid.UUID, include_archived: bool = False):
    if not user_exists(db, user_id):
        return None

    query = db.query(JobModel).filter(JobModel.user_id == user_id)
    if not include_archived:
        query = query.filter(JobModel.archived.is_(False))

    jobs = query.all()
    # Current jobs first, then by the order the student put them in: a job you
    # have left is history and should not sit above one you turn up to.
    jobs.sort(key=lambda job: (job.ended_on is not None, job.position, job.name))
    return [as_schema(job) for job in jobs]


def get_job(db: Session, user_id: uuid.UUID, job_id: uuid.UUID):
    job = owned_job(db, user_id, job_id)
    return None if job is None else as_schema(job)


def create_job(db: Session, user_id: uuid.UUID, data: JobCreate):
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

    db.add(job)
    db.commit()
    db.refresh(job)
    return as_schema(job)


def check_pay_fields(job: JobModel) -> None:
    """The same cross-field rules the create schema enforces, after an edit.

    They cannot live on `JobUpdate`: a patch changing only `kind` has no way to
    see the rate already stored, so a parse-time check would reject an edit that
    is perfectly valid against the row.
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
    job = owned_job(db, user_id, job_id)
    if job is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    schedule = update_data.pop("pay_schedule", None)
    if "kind" in update_data and update_data["kind"] is not None:
        update_data["kind"] = JobKind(update_data["kind"]).value

    for key, value in update_data.items():
        setattr(job, key, value)

    if schedule is not None:
        apply_recurrence(job, data.pay_schedule)

    if job.ended_on and job.started_on and job.ended_on < job.started_on:
        raise ValueError("A job cannot end before it starts")

    check_pay_fields(job)

    db.commit()
    db.refresh(job)
    return as_schema(job)


def delete_job(db: Session, user_id: uuid.UUID, job_id: uuid.UUID):
    """Remove a job, its shift blocks and everything recorded against it.

    Ending a job is `ended_on`; archiving it is `archived`. This is for a job
    entered by mistake, so it takes the calendar blocks with it -- leaving them
    would put shifts on the calendar for an employer that no longer exists.
    """
    job = owned_job(db, user_id, job_id)
    if job is None:
        return None

    removed = as_schema(job)

    db.query(EventModel).filter(
        EventModel.user_id == user_id, EventModel.job_id == job_id
    ).delete(synchronize_session=False)
    db.delete(job)
    db.commit()
    return removed


def shift_window(job: JobModel, data: ShiftScheduleCreate) -> tuple[date, date]:
    """When the pattern runs, preferring the form over the job's own dates."""
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
    """Replace this job's recurring shifts with the pattern given.

    Replace rather than append, matching how a course timetable behaves:
    submitting the form twice after fixing a time must leave one schedule rather
    than two overlapping copies.

    Only this job's own blocks are touched. A one-off shift added straight to
    the calendar for a different job, or a personal event, survives.
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
    """One shift on one date, with no rule behind it.

    The ordinary case for student work, which is rarely the same hours every
    week. A pattern is the exception, and lives in `set_shift_schedule`.

    Written as an event with no recurrence, so the calendar, the free-block
    finder and the earnings figures all see it without knowing it was entered by
    hand rather than generated.
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
    """Delete a shift and anything recorded about it.

    Only a one-off. A date generated by a pattern has no row of its own to
    delete -- cancelling one of those is a skipped date on the rule, which is
    what the calendar already offers. Deleting one that was never confirmed
    is the ordinary case; deleting a confirmed one is for a mistake -- the
    wrong job, the wrong date -- and takes its record, including any cash tip
    already in the ledger, with it.
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
    for record in records:
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
                db.query(TransactionModel).filter(
                    TransactionModel.user_id == user_id,
                    TransactionModel.group_id == anchor.group_id,
                ).delete(synchronize_session=False) if anchor.group_id is not None else db.delete(anchor)
        db.delete(record)

    db.delete(event)
    db.commit()
    return event_id


def records_by_date(
    db: Session, user_id: uuid.UUID, start: date, end: date
) -> dict[tuple[uuid.UUID, date], ShiftRecordModel]:
    """Everything recorded about a shift date in the window, keyed as it is identified."""
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
    """Every shift date in the window, with what is known about each.

    Built on `list_occurrences` rather than a query of its own, so a shift is
    expanded by the same engine that expands a lecture and cannot disagree with
    what the calendar draws.
    """
    expanded = list_occurrences(db, user_id, start, end)
    if expanded is None:
        return None

    jobs = {job.id: job for job in db.query(JobModel).filter(JobModel.user_id == user_id)}
    records = records_by_date(db, user_id, start, end)
    anchor = on_day or today()

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
    """Record what happened on one date of a shift, creating the row or updating it.

    Upsert rather than insert, because `(event_id, on_date)` identifies the
    date and confirming the same Friday twice must not leave two answers to
    what was worked.
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

    record.worked_start = data.worked_start
    record.worked_end = data.worked_end
    record.confirmed = data.confirmed
    record.tip_amount = data.tip_amount
    record.tip_is_cash = data.tip_is_cash
    record.rate_override = data.rate_override
    record.notes = data.notes

    sync_cash_tip(db, user_id, record, event)

    db.commit()
    db.refresh(record)
    return ShiftRecord.model_validate(record)


def sync_cash_tip(
    db: Session, user_id: uuid.UUID, record: ShiftRecordModel, event: EventModel
) -> None:
    """Keep the ledger row for a cash tip in step with the record.

    Cash is money already in hand, so it is the one part of a shift that reaches
    the budget without waiting for a cheque. A tip paid through payroll does not:
    it arrives inside the cheque's gross, and writing a row for it here as well
    would count it twice.

    Written and unwritten rather than only written, because a tip can be
    corrected to zero, or marked as having gone on the cheque after all, and
    either leaves a row that no longer describes anything.
    """
    wants_row = record.tip_amount > 0 and record.tip_is_cash

    # A tip splits across accounts like any other income, so it is several rows
    # tied by a group -- the record points at one of them, and the group is what
    # finds the rest. Deleting only the row it points at would orphan the others.
    anchor = None
    if record.tip_transaction_id is not None:
        anchor = (
            db.query(TransactionModel)
            .filter(
                TransactionModel.id == record.tip_transaction_id,
                TransactionModel.user_id == user_id,
            )
            .first()
        )

    existing = []
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

    if not wants_row:
        for row in existing:
            db.delete(row)
        record.tip_transaction_id = None
        db.flush()
        return

    job = db.query(JobModel).filter(JobModel.id == record.job_id).first()
    description = f"{job.name if job else 'Shift'} tips"

    # Rewritten rather than patched: the amount changed, so the split changed,
    # and reconciling row-by-row against a new split is more ways to be wrong.
    for row in existing:
        db.delete(row)
    record.tip_transaction_id = None
    db.flush()

    # Split like any other income, so cash lands wherever the student has said
    # incoming money goes. A student who wants cash tracked apart can give a
    # cash account its own income share.
    accounts = active_accounts(db, user_id)
    split = split_income(round(record.tip_amount, 2), accounts)
    if not split:
        # No account takes a share, so there is nowhere to put it. Recording the
        # tip on the shift still happens -- refusing would block logging your
        # hours over an unrelated budget setting -- and `tip_in_ledger` says the
        # money has not reached the budget, so the gap is visible rather than
        # silent.
        record.tip_transaction_id = None
        db.flush()
        return

    group_id = uuid.uuid4()
    rows = [
        TransactionModel(
            id=uuid.uuid4(),
            user_id=user_id,
            account_id=entry.account_id,
            kind=INCOME,
            amount=entry.amount,
            description=description,
            occurred_on=record.on_date,
            group_id=group_id,
        )
        for entry in split
        if entry.amount > 0
    ]
    db.add_all(rows)
    db.flush()
    # The first row is what the record points at; the group ties the rest to it.
    record.tip_transaction_id = rows[0].id if rows else None
    db.flush()
