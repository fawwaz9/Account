import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, declarative_base

# app/_database/db.py -> app/_database -> app -> backend
BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = BACKEND_DIR / "data" / "app.db"

# Anchored to the backend directory rather than the process's working
# directory. The old "sqlite:///./app.db" default resolved against wherever
# uvicorn happened to be started, so a local run wrote to backend/app.db while
# docker-compose (DATABASE_URL=sqlite:////app/data/app.db, bind-mounted from
# backend/data) used a different file entirely, and the two silently diverged.
def normalize_database_url(database_url: str) -> str:
    """Let a connection string be pasted from a dashboard and just work.

    Supabase hands you ``postgresql://...`` with no driver named. SQLAlchemy
    resolves a bare ``postgresql://`` to **psycopg2**, which is not installed and
    never will be -- D1.2 chose psycopg 3 -- so copying the string verbatim gives
    you ``ModuleNotFoundError: No module named 'psycopg2'`` at import, which says
    nothing about the actual problem and would be an easy hour to lose at the
    exact moment of first connecting to a real database.

    Only the bare form is rewritten. ``postgresql+psycopg2://`` is left alone,
    because that spelling is someone stating a preference rather than omitting
    one, and silently overriding it would be worse than failing.
    """
    url = make_url(database_url)
    if url.drivername == "postgresql":
        # hide_password=False is essential: str(URL) masks the password as
        # literal asterisks, so rendering the default way would produce a URL
        # that parses fine and cannot authenticate.
        return url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
    return database_url


DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}"))


def connect_args_for(database_url: str) -> dict:
    """The DBAPI arguments this URL's driver will actually accept.

    ``check_same_thread`` is SQLite's alone. It was passed unconditionally, so
    every non-SQLite ``DATABASE_URL`` died at import with psycopg rejecting an
    argument it has never heard of -- while ``docker-compose.yml`` advertised the
    variable as configurable. The database was swappable in documentation only.

    The URL is parsed rather than string-matched: ``make_url`` understands
    ``sqlite+pysqlite://`` and ``postgresql+psycopg://`` alike, where
    ``startswith("sqlite")`` is a guess about a structured value that quietly
    does the wrong thing for the first driver-qualified URL nobody thought of.

    Separate from the engine so it can be tested without one. The bug it fixes
    only ever surfaced on a first connection, which is exactly the moment a test
    cannot reach without a live server.
    """
    # Normalised first, so this is right whatever it is handed. Called with a
    # raw `postgresql://` -- which is exactly what a dashboard gives you, and
    # what conftest reads from TEST_DATABASE_URL -- an un-normalised parse
    # reports the driver as psycopg2 and the psycopg branch below is silently
    # skipped. The engine would then be built without `prepare_threshold`, and
    # the transaction pooler would start failing on the fifth execution of a
    # query rather than immediately.
    url = make_url(normalize_database_url(database_url))
    if url.get_backend_name() == "sqlite":
        return {"check_same_thread": False}

    if url.get_driver_name() == "psycopg":
        # Turns off psycopg's automatic server-side prepared statements, which
        # it starts using after the fifth execution of a query.
        #
        # Supabase's transaction pooler (port 6543) hands each transaction
        # whichever backend connection is free, so the connection that PREPAREd
        # a statement is usually not the one asked to EXECUTE it. The error is
        # "prepared statement ... does not exist", or "already exists" when a
        # name collides -- and it appears only after a query has been run five
        # times, so it survives every smoke test and shows up under real use.
        #
        # The cost is re-planning each query. For this workload that is
        # immaterial; it is also what the pooler requires. On a direct or
        # session-mode connection this is unnecessary but harmless.
        return {"prepare_threshold": None}

    return {}


#: Connections this process keeps open, and how many more it may borrow briefly.
#: Small on purpose: with `max-instances` 3 (D3.3) the whole deployment holds at
#: most 3 x (3 + 2) = 15, which is a comfortable fraction of what the free
#: pooler allows. The 40-thread request pool from D3.4 sits in front of these,
#: so under genuine load threads queue for a connection -- fine here, where a
#: query is milliseconds and real concurrency is two or three.
POOL_SIZE = 3
MAX_OVERFLOW = 2
#: How long a thread waits for a connection before giving up. SQLAlchemy's
#: default is 30 seconds, which is long enough that a starved request looks like
#: a hang rather than an error. Ten seconds is still far more than a healthy
#: checkout needs and fails visibly instead.
POOL_TIMEOUT_SECONDS = 10
#: Drop and remake a connection after half an hour, so nothing in the path --
#: pooler, load balancer, idle timeout -- gets to close one out from under us
#: first.
POOL_RECYCLE_SECONDS = 1800


def engine_kwargs_for(database_url: str) -> dict:
    """Pooling settings, which only mean anything across a network.

    Deliberately empty for SQLite. The file is local, so there is nothing to
    pre-ping and no latency to amortise -- and the in-memory database the tests
    use gets a ``SingletonThreadPool``, which has no concept of overflow and
    would reject the argument outright.

    ``pool_pre_ping`` is the important one. It issues a trivial statement when a
    connection is checked out and quietly replaces it if it has died. Poolers
    drop connections at their own discretion, Cloud Run tears instances down
    constantly, and a Supabase project pauses after seven idle days -- so a
    connection that was good when it was pooled is not necessarily good when it
    is used. Without this, the first request after any of those is a 500 for
    whoever happens to arrive first. D2.4.
    """
    if make_url(database_url).get_backend_name() == "sqlite":
        return {}
    return {
        "pool_pre_ping": True,
        "pool_size": POOL_SIZE,
        "max_overflow": MAX_OVERFLOW,
        "pool_timeout": POOL_TIMEOUT_SECONDS,
        "pool_recycle": POOL_RECYCLE_SECONDS,
    }


#: Whether this process is talking to SQLite. Read below to decide what is worth
#: setting up: the pragmas, and the directory the file needs to live in.
IS_SQLITE = make_url(DATABASE_URL).get_backend_name() == "sqlite"

# Only when the database is a file. A Postgres URL wants no directory, and
# creating one anyway left an empty `data/` beside every deployment that had
# moved off SQLite -- harmless, but it is the same wrong assumption as the
# connect argument above, and worth removing with it.
if IS_SQLITE:
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args_for(DATABASE_URL),
    **engine_kwargs_for(DATABASE_URL),
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

#: How long a writer waits for another writer's lock before giving up, in
#: milliseconds. Without it SQLite raises `database is locked` immediately, and
#: with a 40-thread request pool two simultaneous writes surface that as an
#: uncaught 500 rather than as the momentary contention it actually is.
BUSY_TIMEOUT_MS = 5000


def apply_sqlite_pragmas(dbapi_connection) -> None:
    """The three settings SQLite needs before it behaves like a database.

    Separate from the event hook so the test fixtures can call it against their
    own engine: a test suite running without foreign keys enforced cannot catch
    the orphan it is meant to be guarding against.

    * **WAL** lets readers carry on during a write. On the default journal a
      single write blocks every reader for its duration.
    * **foreign_keys** is OFF by default in SQLite, which means every
      ``ForeignKey`` in models.py is documentation rather than a rule, and a
      cascade that the ORM does not happen to know about leaves orphans.
    * **busy_timeout** is above.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    cursor.close()


# Per connection, not per engine: `foreign_keys` and `busy_timeout` are
# connection-scoped in SQLite, so setting them once at startup would leave every
# later pooled connection without them. Guarded on the dialect so pointing
# DATABASE_URL at anything else does not send SQLite pragmas to it.
if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        apply_sqlite_pragmas(dbapi_connection)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()