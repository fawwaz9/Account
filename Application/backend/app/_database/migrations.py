"""Additive schema fixes for databases created before a column existed.

``Base.metadata.create_all`` only ever creates missing *tables* — it will not
alter one that already exists. An existing ``data/app.db`` therefore keeps the
old shape and every query touching a new column fails with
``no such column``.

Until this project adopts Alembic, new nullable columns are added here. Each
step must be idempotent, since this runs on every startup.
"""

from sqlalchemy import inspect, text

from app._database.db import Base, engine

# Importing the models is what populates Base.metadata, which ensure_indexes
# walks. Without it this module would see an empty metadata and silently create
# nothing.
from app._database import models  # noqa: F401

# table -> column -> DDL type, for columns added after the table's first release
ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "users": {
        "password_hash": "VARCHAR",
        "email_verified": "BOOLEAN NOT NULL DEFAULT 0",
        "preferences": "JSON NOT NULL DEFAULT '{}'",
        "current_school_year": "INTEGER",
        "current_semester": "VARCHAR",
        "term_label": "VARCHAR",
        "first_year_calendar_year": "INTEGER",
        "session_epoch": "INTEGER NOT NULL DEFAULT 0",
        "deleted_at": "DATETIME",
    },
    "courses": {
        "target_grade": "FLOAT",
        # Defaulted at the column so existing rows read as an empty list rather
        # than NULL -- every reader treats this as a list and a NULL would make
        # each one guard for it.
        "links": "JSON NOT NULL DEFAULT '[]'",
        "no_final": "BOOLEAN NOT NULL DEFAULT 0",
        "transfer_credit": "BOOLEAN NOT NULL DEFAULT 0",
        "archived": "BOOLEAN NOT NULL DEFAULT 0",
    },
    "accounts": {
        # NOT "DEFAULT 0"/"DEFAULT 1" like the older booleans above. Postgres
        # refuses an integer default on a boolean column -- "column is of type
        # boolean but default expression is of type integer" -- and this is the
        # first entry here that will ever run as an ALTER against Postgres:
        # every older one predates Supabase, whose tables create_all built from
        # the models with nothing left for ensure_schema to add. The `true`
        # literal is accepted by both SQLite and Postgres.
        "counts_toward_net_worth": "BOOLEAN NOT NULL DEFAULT true",
    },
    "grades": {
        "due_date": "DATE",
        "due_time": "TIME",
        "duration_minutes": "INTEGER",
        "schedule_as": "VARCHAR NOT NULL DEFAULT 'task'",
        "excluded": "BOOLEAN NOT NULL DEFAULT 0",
    },
    "events": {
        "grade_id": "CHAR(32)",
        "job_id": "CHAR(32)",
    },
    "tasks": {
        "recurring_id": "CHAR(32)",
        "priority": "INTEGER NOT NULL DEFAULT 3",
        "snoozed_until": "DATE",
        "occurrence_date": "DATE",
    },
    "recurring_tasks": {
        "priority": "INTEGER NOT NULL DEFAULT 3",
    },
    "transactions": {
        "category_id": "CHAR(32)",
        "recurring_id": "CHAR(32)",
        "course_id": "CHAR(32)",
    },
}

# Run once, immediately after the named column is first added, to give existing
# rows a sensible value.
#
# Keyed by ``(table, column)``, not by column alone. `archived`, `position`,
# `name`, `user_id` and `kind` each exist on several tables, so a bare column
# name would fire one table's backfill against another's new column the moment
# a second entry was added. One entry today is exactly when to fix that.
BACKFILLS: dict[tuple[str, str], str] = {
    # Every pre-existing Google account had its address vouched for by Google
    # at signup, before this column existed.
    ("users", "email_verified"): (
        "UPDATE users SET email_verified = 1 WHERE google_id IS NOT NULL"
    ),
    # Every occurrence written before this column existed was created on its due
    # date and has not been moved, because until now there was no way to move
    # one. Without this they would all read NULL, the materialiser would see an
    # empty set of written dates, and the next task-page load would write the
    # whole rolling window a second time.
    ("tasks", "occurrence_date"): (
        "UPDATE tasks SET occurrence_date = due_date WHERE recurring_id IS NOT NULL"
    ),
}


def ensure_schema() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table, columns in ADDED_COLUMNS.items():
        if table not in existing_tables:
            continue  # create_all just made it with the full set

        present = {column["name"] for column in inspector.get_columns(table)}
        missing = {name: ddl for name, ddl in columns.items() if name not in present}
        if not missing:
            continue

        with engine.begin() as connection:
            for name, ddl in missing.items():
                # Identifiers come from the literal dict above, never user input.
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                backfill = BACKFILLS.get((table, name))
                if backfill is not None:
                    connection.execute(text(backfill))


def ensure_indexes(bind=None) -> None:
    """Create any index declared on a model that the database does not have.

    ``create_all`` builds indexes only for tables it creates, so an existing
    database never gains one added later. This walks the same metadata the
    models declare, which is why there is no second list of index DDL to keep
    in step with models.py.

    A unique index can fail here, and that is the point: it means rows already
    violate it, and inventing a resolution automatically would be worse than
    saying so. The name of the failing index says which rule was broken.

    `bind` defaults to the application engine; the tests pass their own.
    """
    target = bind if bind is not None else engine
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            index.create(bind=target, checkfirst=True)
