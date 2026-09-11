"""Additive schema fixes for databases created before a column existed.

``Base.metadata.create_all`` only ever creates missing *tables* — it will not
alter one that already exists. An existing ``data/app.db`` therefore keeps the
old shape and every query touching a new column fails with
``no such column``.

Until this project adopts Alembic, new nullable columns are added here. Each
step must be idempotent, since this runs on every startup.
"""

from sqlalchemy import inspect, text

from app._database.db import engine

# table -> column -> DDL type, for columns added after the table's first release
ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "users": {
        "password_hash": "VARCHAR",
        "email_verified": "BOOLEAN NOT NULL DEFAULT 0",
        "preferences": "JSON NOT NULL DEFAULT '{}'",
        "current_school_year": "INTEGER",
        "current_semester": "VARCHAR",
        "term_label": "VARCHAR",
        "session_epoch": "INTEGER NOT NULL DEFAULT 0",
    },
    "courses": {
        "target_grade": "FLOAT",
        "no_final": "BOOLEAN NOT NULL DEFAULT 0",
        "transfer_credit": "BOOLEAN NOT NULL DEFAULT 0",
        "archived": "BOOLEAN NOT NULL DEFAULT 0",
    },
    "grades": {
        "due_date": "DATE",
        "schedule_as": "VARCHAR NOT NULL DEFAULT 'task'",
    },
    "events": {
        "grade_id": "CHAR(32)",
    },
    "transactions": {
        "category_id": "CHAR(32)",
        "recurring_id": "CHAR(32)",
    },
}

# Run once, immediately after the named column is first added, to give existing
# rows a sensible value. Keyed by column so it cannot fire twice.
BACKFILLS: dict[str, str] = {
    # Every pre-existing Google account had its address vouched for by Google
    # at signup, before this column existed.
    "email_verified": "UPDATE users SET email_verified = 1 WHERE google_id IS NOT NULL",
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
                backfill = BACKFILLS.get(name)
                if backfill is not None:
                    connection.execute(text(backfill))
