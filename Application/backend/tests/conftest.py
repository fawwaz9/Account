"""Test fixtures: every test gets a clean database, isolated from the next.

Deliberately never uses ``SessionLocal`` or the engine in app._database.db,
which are bound to the real data/app.db file. A test that can reach the live
ledger is worse than no test. The module itself is in the import graph either
way -- models.py imports ``Base`` from it -- and importing it issues no DDL;
what matters is that nothing here binds a session to that engine.

**Which database.** ``TEST_DATABASE_URL`` chooses. Unset, it is SQLite in
memory, which is what it has always been and what keeps the local loop fast.
Set to a Postgres URL, the same suite runs against the database the app will
actually be deployed on -- which is the only way to know the port worked rather
than merely imported.

The two need different isolation, and the difference is worth understanding:

* **SQLite in memory** is free to throw away. Each test builds the whole schema
  into a private database and drops it with the engine, so isolation is total
  and costs nothing.
* **Postgres is not.** Building 23 tables and 49 indexes per test, over a
  network, would take longer than the suite is worth. So the schema is created
  once, and each test runs inside a transaction that is rolled back afterwards.
  ``join_transaction_mode="create_savepoint"`` is what makes that survive the
  application's own ``commit()`` calls: they release a savepoint instead of
  committing, so the code under test behaves normally while the outer
  transaction still rolls everything back.
"""
import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Before anything imports app._database.db, which reads DATABASE_URL once at
# import and binds `engine` and `SessionLocal` to it for the life of the
# process. Unset, that is the real data/app.db -- so a test that reaches the
# application engine reaches the live ledger.
#
# Most of this suite never does: the `db` fixture builds its own engine. But
# anything exercising the ASGI app runs the app's *lifespan*, which issues DDL
# and runs the expired-account purge through `SessionLocal`. That is a delete
# statement against whatever this points at, and "the tests do not use it" is
# an invariant maintained by hand rather than by anything.
#
# Overridden rather than defaulted: there is no legitimate reason for the suite
# to talk to a configured database, and TEST_DATABASE_URL is the knob for
# choosing where the fixtures run.
os.environ["DATABASE_URL"] = f"sqlite:///{Path(tempfile.gettempdir()) / 'account-suite-app.db'}"

from app._database.db import (  # noqa: E402
    apply_sqlite_pragmas,
    connect_args_for,
    engine_kwargs_for,
    normalize_database_url,
)
from app._database.models import (  # noqa: E402
    AccountModel,
    Base,
    CourseCategoryWeightModel,
    CourseModel,
    SpendCategoryModel,
    UserModel,
)


#: Unset means SQLite in memory, which is the default for a reason: it needs no
#: server, no cleanup and no network, so the suite stays a two-second feedback
#: loop. Point it at Postgres to run the same tests against the real thing.
#: Normalised the same way the app normalises its own URL, so a connection
#: string pasted straight from the Supabase dashboard works here too -- and so
#: the suite exercises the same driver the deployment will use.
TEST_DATABASE_URL = normalize_database_url(os.getenv("TEST_DATABASE_URL", "sqlite://"))
TESTING_SQLITE = make_url(TEST_DATABASE_URL).get_backend_name() == "sqlite"

#: Hosts a throwaway database plausibly lives on. A Postgres container published
#: on 127.0.0.1 is here; anything reached over a network is not.
LOCAL_HOSTS = {None, "", "localhost", "127.0.0.1", "::1", "host.docker.internal"}


def is_local_database(database_url: str) -> bool:
    """Whether losing everything in this database would cost nothing."""
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        return True
    return url.host in LOCAL_HOSTS


def allows_remote_testing() -> bool:
    return os.getenv("TEST_DATABASE_ALLOW_REMOTE", "").strip().lower() in {"1", "true", "yes", "on"}


# The suite is destructive by design: `_pg_engine` runs `drop_all` before the
# first test and again after the last, because a run that inherits rows from the
# previous one is not a clean run.
#
# That is correct against a container and catastrophic against the deployed
# database. The two are one environment variable apart, and the dangerous one is
# the shorter thing to type -- so after step 20 puts the real data in Supabase,
# `TEST_DATABASE_URL=$SUPABASE_DATABASE_URL pytest` is a command that looks
# entirely reasonable and destroys everything.
#
# Refused at collection rather than warned about, and refused before any
# connection is opened. Setting TEST_DATABASE_ALLOW_REMOTE is the deliberate act
# that says the target really is disposable.
if not is_local_database(TEST_DATABASE_URL) and not allows_remote_testing():
    raise pytest.UsageError(
        f"TEST_DATABASE_URL points at a remote host ({make_url(TEST_DATABASE_URL).host}).\n"
        "\n"
        "This suite DROPS EVERY TABLE before it starts and again when it finishes.\n"
        "Against a container that is correct. Against a database holding real data\n"
        "it is unrecoverable, and this project has no automated backups yet.\n"
        "\n"
        "If that database is genuinely disposable -- a fresh Supabase project with\n"
        "nothing in it yet, which is exactly what step 19 is for -- say so:\n"
        "\n"
        "    TEST_DATABASE_ALLOW_REMOTE=1 TEST_DATABASE_URL=... pytest\n"
    )


def _make_engine(url: str):
    # The app's own pooling settings, so a Postgres run here is configured the
    # way the deployment is rather than on SQLAlchemy's defaults. Empty for
    # SQLite, which is what lets StaticPool below be set without a conflict.
    kwargs = {"connect_args": connect_args_for(url), **engine_kwargs_for(url)}
    if make_url(url).get_backend_name() == "sqlite":
        # One shared connection, or ":memory:" gives each connection its own
        # empty database and create_all appears to have done nothing.
        kwargs["poolclass"] = StaticPool

    engine = create_engine(url, **kwargs)

    if make_url(url).get_backend_name() == "sqlite":
        # The same pragmas the real engine sets, so the suite runs under the
        # rules the app runs under. Without foreign_keys ON here, every cascade
        # test passes whether or not the cascade is actually enforced. Postgres
        # needs none of this -- it has no switch for its own constraints.
        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_connection, _record):
            apply_sqlite_pragmas(dbapi_connection)

    return engine


#: For the handful of tests that are about SQLite itself rather than about the
#: application -- its pragmas, and a legacy state only a pre-enforcement SQLite
#: file can hold. Skipped rather than rewritten, because on Postgres they are
#: asserting something that cannot be true there.
sqlite_only = pytest.mark.skipif(
    not TESTING_SQLITE, reason="about SQLite specifically, not about the app"
)


@pytest.fixture(scope="session")
def _pg_engine():
    """One engine and one schema for the whole Postgres run.

    Session-scoped because the expensive part is the DDL, not the connection:
    23 tables and 49 indexes built once instead of 669 times. Dropped at the
    end so a re-run starts clean rather than inheriting whatever the last one
    left when it crashed.
    """
    engine = _make_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def db(request):
    if TESTING_SQLITE:
        engine = _make_engine(TEST_DATABASE_URL)
        Base.metadata.create_all(bind=engine)
        session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
        try:
            yield session
        finally:
            session.close()
            engine.dispose()
        return

    # Postgres: keep the schema, throw away the rows. The session joins an
    # outer transaction that is rolled back at the end, so nothing a test wrote
    # -- committed or not -- is visible to the next one.
    engine = request.getfixturevalue("_pg_engine")
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=connection,
        join_transaction_mode="create_savepoint",
    )()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def user(db):
    return make_user(db, "owner@example.com")


def make_user(db, email: str) -> UserModel:
    row = UserModel(id=uuid.uuid4(), name=email.split("@")[0], email=email, email_verified=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def make_account(
    db,
    user_id: uuid.UUID,
    name: str,
    share: float = 0.0,
    kind: str = "spending",
    archived: bool = False,
) -> AccountModel:
    row = AccountModel(
        id=uuid.uuid4(), user_id=user_id, name=name, kind=kind,
        income_share=share, archived=archived, position=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def make_category(db, user_id: uuid.UUID, name: str) -> SpendCategoryModel:
    row = SpendCategoryModel(
        id=uuid.uuid4(), user_id=user_id, name=name, archived=False, position=0
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def make_course(db, user_id: uuid.UUID, code: str, **overrides) -> CourseModel:
    fields = {
        "name": f"{code} course", "semester": "Fall", "year": 3, "credits": 3.0,
        "required": True, "final_grade": 0.0, "average": 0.0,
        "no_final": False, "transfer_credit": False, "archived": False,
    }
    weights = overrides.pop("category_weights", {"Assignment": 50.0, "Final": 50.0})
    fields.update(overrides)

    row = CourseModel(id=uuid.uuid4(), user_id=user_id, code=code, **fields)
    db.add(row)
    db.flush()
    for category, weight in weights.items():
        db.add(CourseCategoryWeightModel(course_id=row.id, category=category, weight=weight))
    db.commit()
    db.refresh(row)
    return row
