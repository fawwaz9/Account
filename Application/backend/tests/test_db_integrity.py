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
from app._database.db import (
    IS_SQLITE,
    connect_args_for,
    engine,
    engine_kwargs_for,
    normalize_database_url,
)
from tests.conftest import sqlite_only
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
 utc_now,
)
from app.Finances.services.account_service import delete_account
from app.Users.schemas.user import DELETION_GRACE_DAYS
from app.Users.services.user_service import delete_user, purge_expired_users
from conftest import make_account, make_course, make_user
from datetime import date, timedelta


# ------------------------------------------------------- foreign keys are on --

@sqlite_only
def test_foreign_keys_are_enforced(db):
    """Off by default in SQLite, which makes every ForeignKey documentation.

    SQLite only, and deliberately so: Postgres has no switch to check. The test
    immediately below asserts the *behaviour* instead, and that one is worth far
    more because it passes on both and would catch the pragma silently failing.
    """
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

def test_purging_a_user_leaves_nothing_behind(db, user):
    """Every table the user owns, not just the two that were listed.

    Goes through the purge rather than `delete_user`, because deletion is a
    request now: `delete_user` marks the account and the purge is what actually
    removes it once the grace period has run out. The cascades this asserts are
    the purge's to honour.
    """
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
    # Far enough past the deadline that the account is due to go. Dated from
    # `utc_now()`, not `date.today()`: `deleted_at` is stamped in UTC, so a local
    # date disagrees with it for part of every day -- which made this pass in the
    # morning and fail in the evening anywhere behind UTC.
    purge_expired_users(
        db, on_day=utc_now().date() + timedelta(days=DELETION_GRACE_DAYS + 1)
    )

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

def index_names(bind, table: str) -> set[str]:
    return {index["name"] for index in inspect(bind).get_indexes(table)}


def test_ensure_indexes_adds_what_an_older_database_lacks(db):
    """create_all only indexes tables it creates, so an existing one gains none.

    Works through `db.connection()` rather than `db.get_bind()`. The two are the
    same thing on SQLite, where the session is bound to an engine -- but against
    Postgres the session is bound to a connection inside the test's transaction,
    and opening a second one with `engine.begin()` deadlocks against it. The
    session's own connection is the one object that means the same thing on
    both, and it keeps the dropped index inside the rollback.
    """
    connection = db.connection()
    connection.execute(text("DROP INDEX ix_transactions_account_id"))
    assert "ix_transactions_account_id" not in index_names(connection, "transactions")

    ensure_indexes(bind=connection)

    assert "ix_transactions_account_id" in index_names(connection, "transactions")


def test_ensure_indexes_is_safe_to_run_twice(db):
    """It runs on every startup, so it has to be idempotent."""
    connection = db.connection()

    ensure_indexes(bind=connection)
    ensure_indexes(bind=connection)

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


# ------------------------------------------- the engine is dialect-agnostic --

def test_sqlite_gets_the_argument_only_sqlite_accepts():
    assert connect_args_for("sqlite:///./app.db") == {"check_same_thread": False}
    # Driver-qualified, which a startswith("sqlite") check would also catch --
    # included so the parsing is not accidentally equivalent to string matching.
    assert connect_args_for("sqlite+pysqlite:///./app.db") == {"check_same_thread": False}


def test_postgres_gets_no_sqlite_arguments():
    """The bug this replaces: `check_same_thread` went to every driver.

    psycopg rejects unknown connection options outright, so passing it made any
    non-SQLite DATABASE_URL fail on its first connection -- while compose
    advertised the variable as configurable.
    """
    for url in ("postgresql+psycopg://user:pw@host:5432/app", "postgresql://user:pw@host/app"):
        assert "check_same_thread" not in connect_args_for(url)


# ------------------------------------------ configured for a remote database --

def test_psycopg_is_told_not_to_prepare_statements():
    """What Supabase's transaction pooler requires.

    It hands each transaction whichever backend connection is free, so the
    connection that PREPAREd a statement is usually not the one asked to EXECUTE
    it. psycopg starts preparing automatically at the fifth execution of a
    query, which is why this failure survives every smoke test and only appears
    under real use.
    """
    assert connect_args_for("postgresql+psycopg://user:pw@host:6543/app") == {
        "prepare_threshold": None
    }


def test_a_url_pasted_from_the_dashboard_gets_the_same_treatment():
    """Supabase hands you `postgresql://`, with no driver named.

    Without normalising first, the parse reports the driver as psycopg2, the
    psycopg branch is skipped, and the engine is built without the setting --
    silently, and only wrong on the fifth execution.
    """
    assert connect_args_for("postgresql://user:pw@host:6543/app") == {
        "prepare_threshold": None
    }


def test_an_explicit_psycopg2_url_is_left_alone():
    """Naming the driver is stating a preference, not omitting one.

    `prepare_threshold` is a psycopg 3 argument; psycopg2 would reject it. The
    driver is not installed either way, but quietly overriding what someone
    wrote is worse than letting it fail where they can see why.
    """
    assert connect_args_for("postgresql+psycopg2://user:pw@host/app") == {}
    assert normalize_database_url("postgresql+psycopg2://user:pw@host/app") == (
        "postgresql+psycopg2://user:pw@host/app"
    )


def test_the_bare_postgres_url_is_pointed_at_the_driver_that_is_installed():
    assert normalize_database_url("postgresql://user:pw@host:6543/postgres") == (
        "postgresql+psycopg://user:pw@host:6543/postgres"
    )


def test_normalising_keeps_the_password():
    """`str(URL)` masks it as literal asterisks.

    Rendering the default way produces a URL that parses perfectly and cannot
    authenticate -- the kind of failure that reads as "wrong password" and sends
    you to reset a password that was correct all along.
    """
    normalized = normalize_database_url("postgresql://postgres.abc:s3cr3t-pw@host:6543/postgres")
    assert "s3cr3t-pw" in normalized
    assert "*" not in normalized


def test_sqlite_urls_are_untouched():
    for url in ("sqlite://", "sqlite:///./app.db", "sqlite+pysqlite:///./app.db"):
        assert normalize_database_url(url) == url


def test_sqlite_gets_no_pooling_settings():
    """There is nothing to pre-ping in a local file.

    And the in-memory database the suite runs on gets a SingletonThreadPool,
    which has no concept of overflow and rejects the argument outright -- so
    this is load-bearing for the test suite, not only tidiness.
    """
    assert engine_kwargs_for("sqlite://") == {}
    assert engine_kwargs_for("sqlite:///./app.db") == {}


def test_a_remote_database_gets_pre_ping_and_a_small_pool():
    """The connection that was good when it was pooled may not be when used.

    Poolers drop connections at their own discretion, Cloud Run tears instances
    down constantly, and a Supabase project pauses after seven idle days.
    Without pre-ping the first request after any of those is a 500 for whoever
    arrives first.
    """
    kwargs = engine_kwargs_for("postgresql+psycopg://user:pw@host:6543/app")

    assert kwargs["pool_pre_ping"] is True
    # Small on purpose: max-instances 3 x (pool_size + max_overflow) is the
    # whole deployment's connection ceiling, and it has to stay well inside what
    # the free pooler allows.
    assert kwargs["pool_size"] + kwargs["max_overflow"] <= 8
    # Shorter than SQLAlchemy's 30s default, so a starved request fails visibly
    # instead of looking like a hang.
    assert kwargs["pool_timeout"] < 30


def test_the_engine_was_built_with_what_these_functions_say():
    """Guards the functions and the engine drifting apart.

    Both are correct in isolation and the engine could still have been
    constructed without them, which is the failure this catches.
    """
    if IS_SQLITE:
        assert engine.pool._pre_ping is False
    else:
        assert engine.pool._pre_ping is True


def test_the_running_engine_matches_its_url():
    """Whatever this process is pointed at, the two agree.

    Guards the constant and the engine drifting apart -- IS_SQLITE decides
    whether the pragmas are installed, and a stale one would silently run
    SQLite without foreign keys enforced.
    """
    assert IS_SQLITE == (engine.dialect.name == "sqlite")
