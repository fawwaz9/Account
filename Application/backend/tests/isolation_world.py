"""One row in every table, all belonging to one user.

The isolation suite needs a victim who owns *something* everywhere: a route can
only be shown not to leak a kind of row if a row of that kind exists to leak.
Built straight through the ORM rather than through the API, so the world does
not depend on the routes it is about to be used to test.

Every free-text column carries ``marker``, so "did anything of B's reach A" is a
substring check on the response, whatever shape the route returns.
"""
import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select

from app._database.models import (
    AccountCategoryLimitModel,
    AccountCategoryMonthLimitModel,
    AccountModel,
    AccountMonthValueModel,
    Base,
    BudgetTargetModel,
    CourseCategoryWeightModel,
    CourseModel,
    EventModel,
    GradeModel,
    JobModel,
    PaychequeDeductionModel,
    PaychequeModel,
    RecurringTaskModel,
    RecurringTransactionModel,
    ReminderModel,
    ShiftRecordModel,
    SinkingContributionModel,
    SinkingFundModel,
    SpendCategoryModel,
    TaskModel,
    TaskSnoozeModel,
    TermBlackoutModel,
    TransactionModel,
    TuitionDeductionModel,
    TuitionPaymentModel,
)

BYDAY = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def seed_world(db, user_id: uuid.UUID, marker: str, day: date) -> dict[str, uuid.UUID]:
    """Give ``user_id`` one row in every table. Returns ``{table name: row id}``.

    Everything happens on ``day`` -- pass the user's today. Lists default to a
    window around now (this month's transactions, this week's events), and a
    world dated anywhere else is invisible to them, so a list that leaked every
    user's rows would still pass.
    """
    WORLD_DAY = day
    WORLD_MONTH = day.replace(day=1)
    ids: dict[str, uuid.UUID] = {}

    def add(row):
        db.add(row)
        db.flush()
        ids[row.__tablename__] = row.id
        return row

    def new_id():
        return uuid.uuid4()

    account = add(AccountModel(
        id=new_id(), user_id=user_id, name=f"{marker} chequing", kind="spending",
        income_share=100.0, archived=False, position=0,
    ))
    savings = AccountModel(
        id=new_id(), user_id=user_id, name=f"{marker} savings", kind="savings",
        income_share=0.0, archived=False, position=1,
    )
    db.add(savings)
    db.flush()
    ids["accounts_second"] = savings.id

    category = add(SpendCategoryModel(
        id=new_id(), user_id=user_id, name=f"{marker} groceries", archived=False, position=0,
    ))
    course = add(CourseModel(
        id=new_id(), user_id=user_id, code=f"{marker.upper()}101", name=f"{marker} course",
        semester="Fall", year=3, credits=3.0, required=True, professor=f"{marker} prof",
        final_grade=0.0, average=0.0, no_final=False, transfer_credit=False, archived=False,
        links=[{"title": f"{marker} link", "url": f"https://example.com/{marker}"}],
        start_date=day - timedelta(days=14), end_date=day + timedelta(days=60),
    ))
    # The one table with an integer key, so the database assigns it.
    add(CourseCategoryWeightModel(course_id=course.id, category="Assignment", weight=100.0))
    grade = add(GradeModel(
        id=new_id(), course_id=course.id, name=f"{marker} assignment", category="Assignment",
        score=80.0, max_score=100.0, excluded=False, due_date=WORLD_DAY,
    ))
    job = add(JobModel(
        id=new_id(), user_id=user_id, name=f"{marker} job", employer=f"{marker} employer",
        kind="hourly", hourly_rate=20.0, started_on=day - timedelta(days=30), archived=False, position=0,
    ))
    add(TermBlackoutModel(
        id=new_id(), user_id=user_id, label=f"{marker} break",
        starts_on=day + timedelta(days=30), ends_on=day + timedelta(days=34),
    ))
    add(AccountCategoryLimitModel(
        id=new_id(), user_id=user_id, account_id=account.id, category_id=category.id, limit_amount=200.0,
    ))
    add(AccountCategoryMonthLimitModel(
        id=new_id(), user_id=user_id, account_id=account.id, category_id=category.id,
        month=WORLD_MONTH, limit_amount=150.0,
    ))
    add(AccountMonthValueModel(
        id=new_id(), user_id=user_id, account_id=account.id, month=WORLD_MONTH,
        difference_amount=12.5, market_value=1012.5,
    ))
    add(BudgetTargetModel(
        id=new_id(), user_id=user_id, account_id=account.id, month=WORLD_MONTH, planned_amount=300.0,
    ))
    paycheque = add(PaychequeModel(
        id=new_id(), user_id=user_id, job_id=job.id, occurred_on=WORLD_DAY, gross_amount=400.0,
        notes=f"{marker} cheque",
    ))
    add(PaychequeDeductionModel(id=new_id(), paycheque_id=paycheque.id, description=f"{marker} tax", amount=40.0))
    recurring_task = add(RecurringTaskModel(
        id=new_id(), user_id=user_id, course_id=course.id, title=f"{marker} weekly reading",
        notes=f"{marker} notes", starts_on=WORLD_DAY, recur_freq="weekly", recur_interval=1,
        recur_byday=BYDAY[day.weekday()], active=True,
    ))
    recurring_money = add(RecurringTransactionModel(
        id=new_id(), user_id=user_id, kind="expense", account_id=account.id, amount=15.0,
        description=f"{marker} subscription", category_id=category.id, starts_on=WORLD_DAY,
        recur_freq="monthly", recur_interval=1, active=True,
    ))
    add(ReminderModel(
        id=new_id(), user_id=user_id, title=f"{marker} reminder", notes=f"{marker} notes",
        remind_at=datetime.combine(day, time(9, 0), tzinfo=timezone.utc), course_id=course.id,
    ))
    fund = add(SinkingFundModel(
        id=new_id(), user_id=user_id, name=f"{marker} fund", target_amount=500.0,
        due_on=day + timedelta(days=180), from_account_id=account.id, to_account_id=savings.id, archived=False,
    ))
    add(SinkingContributionModel(id=new_id(), fund_id=fund.id, for_month=WORLD_MONTH, amount=50.0))
    event = add(EventModel(
        id=new_id(), user_id=user_id, course_id=course.id, title=f"{marker} lecture", kind="lecture",
        location=f"{marker} hall", notes=f"{marker} notes", starts_on=WORLD_DAY,
        start_time=time(10, 0), end_time=time(11, 0), recur_freq="weekly", recur_interval=1,
        recur_byday=BYDAY[day.weekday()],
    ))
    shift_event = EventModel(
        id=new_id(), user_id=user_id, job_id=job.id, title=f"{marker} shift", kind="shift",
        starts_on=WORLD_DAY, start_time=time(17, 0), end_time=time(21, 0),
    )
    db.add(shift_event)
    db.flush()
    ids["events_shift"] = shift_event.id
    task = add(TaskModel(
        id=new_id(), user_id=user_id, course_id=course.id, grade_id=grade.id, title=f"{marker} task",
        notes=f"{marker} notes", due_date=WORLD_DAY, done=False, archived=False,
    ))
    transaction = add(TransactionModel(
        id=new_id(), user_id=user_id, account_id=account.id, kind="expense", amount=25.0,
        description=f"{marker} coffee", occurred_on=WORLD_DAY, category_id=category.id,
        recurring_id=recurring_money.id,
    ))
    add(ShiftRecordModel(
        id=new_id(), user_id=user_id, event_id=shift_event.id, job_id=job.id, on_date=WORLD_DAY,
        confirmed=True, tip_amount=10.0, tip_is_cash=True, notes=f"{marker} shift notes",
    ))
    add(TaskSnoozeModel(id=new_id(), task_id=task.id, until=day + timedelta(days=6), reason=f"{marker} reason"))
    tuition_txn = TransactionModel(
        id=new_id(), user_id=user_id, account_id=account.id, kind="expense", amount=3000.0,
        description=f"{marker} tuition", occurred_on=WORLD_DAY, course_id=course.id,
    )
    db.add(tuition_txn)
    db.flush()
    ids["transactions_tuition"] = tuition_txn.id
    payment = add(TuitionPaymentModel(
        id=new_id(), user_id=user_id, transaction_id=tuition_txn.id, school_year=3, semester="Fall",
        cost_per_credit=1000.0, fees=0.0, credits_counted=3.0, occurred_on=WORLD_DAY,
    ))
    add(TuitionDeductionModel(
        id=new_id(), tuition_payment_id=payment.id, description=f"{marker} bursary", amount=100.0,
    ))
    _ = (event, transaction, recurring_task)

    db.commit()

    missing = {t.name for t in Base.metadata.sorted_tables} - set(ids) - {"users"}
    assert not missing, f"the world has nothing in: {sorted(missing)}"
    return ids


def snapshot(db) -> dict[str, dict]:
    """Every row of every table, keyed by table and primary key.

    Read through the session's connection so it sees what the routes committed,
    not what the session happens to have cached.
    """
    db.expire_all()
    out = {}
    for table in Base.metadata.sorted_tables:
        rows = db.execute(select(table)).mappings().all()
        out[table.name] = {row["id"]: dict(row) for row in rows}
    return out
