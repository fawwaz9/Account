"""Database engine, session factory and declarative base, built from `DATABASE_URL`.

The URL defaults to the SQLite file `backend/data/app.db`; production points it at
Supabase Postgres through the transaction-mode pooler. The helpers here pick the
driver arguments and pool settings each backend needs, and SQLite connections get
their pragmas as they open. `get_db` is the request-scoped session dependency
behind `DBSession`.
"""

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
    """Return the URL with a bare `postgresql://` scheme pointed at psycopg 3.

    SQLAlchemy reads a bare `postgresql://` as psycopg2, which is not installed, so a
    string pasted from the Supabase dashboard would fail at import.

    Args:
        database_url: Any SQLAlchemy URL string.

    Returns:
        `postgresql+psycopg://...` with the password kept in clear when the driver was
        bare `postgresql`; otherwise the input unchanged, including an explicitly named
        driver such as `postgresql+psycopg2`.
    """
    url = make_url(database_url)
    if url.drivername == "postgresql":
        # hide_password=False is essential: str(URL) masks the password as
        # literal asterisks, so rendering the default way would produce a URL
        # that parses fine and cannot authenticate.
        return url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
    return database_url


DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}"))
"""Normalised connection URL: `DATABASE_URL` if set, else the local SQLite file."""


def connect_args_for(database_url: str) -> dict:
    """Return the DBAPI `connect_args` the URL's driver accepts.

    The URL is normalised first, so a bare `postgresql://` gets the psycopg arguments.

    Args:
        database_url: Any SQLAlchemy URL string.

    Returns:
        `{"check_same_thread": False}` for SQLite, `{"prepare_threshold": None}` for
        psycopg, and an empty dict for any other driver.

    Note:
        `prepare_threshold=None` turns off server-side prepared statements, which a
        transaction-mode pooler cannot keep between transactions.
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
    """Return the connection-pool keyword arguments for `create_engine`.

    Args:
        database_url: Any SQLAlchemy URL string.

    Returns:
        An empty dict for SQLite; otherwise `pool_pre_ping` plus the size, overflow,
        timeout and recycle values from this module's pool constants.
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
    """Turn on WAL, foreign keys and the busy timeout for one SQLite connection.

    Args:
        dbapi_connection: A raw `sqlite3` connection.

    Note:
        All three settings are per connection, so they must run on every new one; the
        test fixtures call this directly on their own engine.
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
        """Apply `apply_sqlite_pragmas` to each connection the SQLite engine opens."""
        apply_sqlite_pragmas(dbapi_connection)

def get_db():
    """Yield a database session for one request and close it when the request ends.

    Yields:
        A new `Session` from `SessionLocal`; closing it rolls back anything left
        uncommitted.

    Note:
        The session carries no acting user. `get_current_user` calls `act_as` on it;
        without that, row security on Postgres returns no rows.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()