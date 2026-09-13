"""The rules the database enforces for itself.

Every one of these was enforced only by Python before -- a check-then-insert
that races, a cascade the ORM happened to know about, an ordering that worked
by accident. A test here fails if the constraint is removed, which is the point:
the previous arrangement passed its tests whether or not the rule held.
"""
import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app._database.migrations import BACKFILLS, ensure_indexes
from app._database.models import (
    AccountModel,
    BudgetTargetModel,
    CourseModel,
    EventModel,
    JobModel,
    RecurringTransactionModel,
    SinkingFundModel,
    SpendCategoryModel,
    TransactionModel,
    UserModel,
)
from app.Finances.services.account_service import delete_account
from app.Users.services.user_service import delete_user
from conftest import make_account, make_course, make_user
from datetime import date


# ------------------------------------------------------- foreign keys are on --

def test_foreign_keys_are_enforced(db):
    """Off by default in SQLite, which makes every ForeignKey documentation."""
    assert db.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_a_row_cannot_point_at_a_user_that_does_not_exist(db):
    db.add(CourseModel(
        id=uuid.uuid4(), user_id=uuid.uuid4(), code="GHOST 100", name="Nobody's course",
        semester="Fall", year=1, credits=3.0,
    ))
    with pytest.raises(IntegrityError):
        db.commit()


# ----------------------------------------------------------------- uniqueness --

def test_two_courses_cannot_share_a_code(db, user):
    make_course(db, user.id, "COSC 111")
    with pytest.raises(IntegrityError):
        make_course(db, user.id, "COSC 111")


def test_two_users_can_hold_the_same_course_code(db, user):
    """The constraint is per user, not global."""
    other = make_user(db, "other@example.com")
    make_course(db, user.id, "COSC 111")
    make_course(db, other.id, "COSC 111")

    assert db.query(CourseModel).count() == 2


def test_two_accounts_cannot_share_a_name(db, user):
    make_account(db, user.id, "Chequing")
    with pytest.raises(IntegrityError):
        make_account(db, user.id, "Chequing")


def test_two_categories_cannot_share_a_name(db, user):
    db.add(SpendCategoryModel(id=uuid.uuid4(), user_id=user.id, name="Food"))
    db.commit()

    db.add(SpendCategoryModel(id=uuid.uuid4(), user_id=user.id, name="Food"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_one_account_gets_one_target_per_month(db, user):
    account = make_account(db, user.id, "Chequing")
    month = date(2026, 9, 1)
    db.add(BudgetTargetModel(
        id=uuid.uuid4(), user_id=user.id, account_id=account.id,
        month=month, planned_amount=400.0,
    ))
    db.commit()

    db.add(BudgetTargetModel(
        id=uuid.uuid4(), user_id=user.id, account_id=account.id,
        month=month, planned_amount=900.0,
    ))
    with pytest.raises(IntegrityError):
        db.commit()


def test_the_same_account_may_have_a_target_in_another_month(db, user):
    account = make_account(db, user.id, "Chequing")
    for month in (date(2026, 9, 1), date(2026, 10, 1)):
        db.add(BudgetTargetModel(
            id=uuid.uuid4(), user_id=user.id, account_id=account.id,
            month=month, planned_amount=400.0,
        ))
    db.commit()

    assert db.query(BudgetTargetModel).count() == 2


# -------------------------------------------------------- deleting a user --

def test_deleting_a_user_leaves_nothing_behind(db, user):
    """Every table the user owns, not just the two that were listed."""
    account = make_account(db, user.id, "Chequing")
    make_course(db, user.id, "COSC 111")
    db.add(SpendCategoryModel(id=uuid.uuid4(), user_id=user.id, name="Food"))
    db.add(BudgetTargetModel(
        id=uuid.uuid4(), user_id=user.id, account_id=account.id,
        month=date(2026, 9, 1), planned_amount=400.0,
    ))
    db.add(JobModel(id=uuid.uuid4(), user_id=user.id, name="Bookstore", kind="hourly"))
    db.add(EventModel(
        id=uuid.uuid4(), user_id=user.id, title="Study", kind="personal",
        starts_on=date(2026, 9, 1),
    ))
    db.add(TransactionModel(
        id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind="income",
        amount=100.0, description="Opening", occurred_on=date(2026, 9, 1),
    ))
    db.commit()

    delete_user(db, user.id)

    for model in (
        UserModel, AccountModel, CourseModel, SpendCategoryModel,
        BudgetTargetModel, JobModel, EventModel, TransactionModel,
    ):
        assert db.query(model).count() == 0, f"{model.__name__} rows survived"


# ----------------------------------------------------- deleting an account --

def test_an_account_with_a_standing_instruction_is_refused(db, user):
    account = make_account(db, user.id, "Chequing")
    db.add(RecurringTransactionModel(
        id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind="expense",
        amount=12.0, description="Spotify", starts_on=date(2026, 9, 1),
        skipped_dates=[], active=True,
    ))
    db.commit()

    with pytest.raises(ValueError, match="standing instruction"):
        delete_account(db, user.id, account.id)


def test_an_account_a_sinking_fund_uses_is_refused(db, user):
    spending = make_account(db, user.id, "Chequing")
    savings = make_account(db, user.id, "Savings")
    db.add(SinkingFundModel(
        id=uuid.uuid4(), user_id=user.id, name="Laptop", target_amount=1200.0,
        due_on=date(2027, 1, 1), from_account_id=spending.id, to_account_id=savings.id,
    ))
    db.commit()

    with pytest.raises(ValueError, match="sinking fund"):
        delete_account(db, user.id, savings.id)


def test_deleting_an_account_takes_its_budget_targets(db, user):
    """A target is a planning number for one account, not history to keep."""
    account = make_account(db, user.id, "Chequing")
    db.add(BudgetTargetModel(
        id=uuid.uuid4(), user_id=user.id, account_id=account.id,
        month=date(2026, 9, 1), planned_amount=400.0,
    ))
    db.commit()

    delete_account(db, user.id, account.id)

    assert db.query(BudgetTargetModel).count() == 0
    assert db.query(AccountModel).count() == 0


# ------------------------------------------------------------------ indexes --

def index_names(engine, table: str) -> set[str]:
    return {index["name"] for index in inspect(engine).get_indexes(table)}


def test_ensure_indexes_adds_what_an_older_database_lacks(db):
    """create_all only indexes tables it creates, so an existing one gains none."""
    engine = db.get_bind()
    db.commit()
    with engine.begin() as connection:
        connection.execute(text("DROP INDEX ix_transactions_account_id"))
    assert "ix_transactions_account_id" not in index_names(engine, "transactions")

    ensure_indexes(bind=engine)

    assert "ix_transactions_account_id" in index_names(engine, "transactions")


def test_ensure_indexes_is_safe_to_run_twice(db):
    """It runs on every startup, so it has to be idempotent."""
    engine = db.get_bind()
    db.commit()

    ensure_indexes(bind=engine)
    ensure_indexes(bind=engine)

    assert "ix_transactions_account_id" in index_names(engine, "transactions")


def test_every_foreign_key_column_is_indexed(db):
    """The rule the index block states, checked rather than trusted.

    A foreign key with no index means every join and every cascade cleanup
    through it is a full table scan.
    """
    engine = db.get_bind()
    inspector = inspect(engine)
    missing = []

    for table in sorted(inspector.get_table_names()):
        indexed_first_columns = {
            index["column_names"][0]
            for index in inspector.get_indexes(table)
            if index["column_names"]
        }
        for key in inspector.get_foreign_keys(table):
            column = key["constrained_columns"][0]
            if column not in indexed_first_columns:
                missing.append(f"{table}.{column}")

    assert missing == []


def test_backfills_are_keyed_by_table_and_column(db):
    """A bare column name would fire one table's backfill at another's column.

    `archived`, `position`, `name`, `user_id` and `kind` each exist on several
    tables, so the key has to say which one.
    """
    assert all(isinstance(key, tuple) and len(key) == 2 for key in BACKFILLS)
