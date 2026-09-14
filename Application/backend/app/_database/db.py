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
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")


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
    if make_url(database_url).get_backend_name() == "sqlite":
        return {"check_same_thread": False}
    return {}


#: Whether this process is talking to SQLite. Read below to decide what is worth
#: setting up: the pragmas, and the directory the file needs to live in.
IS_SQLITE = make_url(DATABASE_URL).get_backend_name() == "sqlite"

# Only when the database is a file. A Postgres URL wants no directory, and
# creating one anyway left an empty `data/` beside every deployment that had
# moved off SQLite -- harmless, but it is the same wrong assumption as the
# connect argument above, and worth removing with it.
if IS_SQLITE:
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args=connect_args_for(DATABASE_URL))
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