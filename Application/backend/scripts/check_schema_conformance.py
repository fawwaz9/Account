"""Deploy gate: check the database has every table, column and function the code needs.

    SCHEMA_CHECK_URL=postgresql://... python scripts/check_schema_conformance.py

Production never applies schema on startup, so the deploy workflow runs this first:
it compares the models' metadata, and the names in `rls.FUNCTIONS`, with what the
database actually has, and prints the schema step to run when something is missing.
Read-only, through the system catalogues, so a CONNECT-only role is enough.

Exits 0 when everything is present, 1 when anything is missing, and 2 when the
check could not mean anything: no URL, too few tables in the models or the
database, or no connection.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Before anything imports app._database.db, which binds a module-level engine to
# DATABASE_URL at import -- and unset, that is the real data/app.db. This script
# never uses that engine, so it is pointed somewhere that cannot matter, whatever
# the caller's environment says.
os.environ["DATABASE_URL"] = "sqlite://"

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine, inspect, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app._database.db import Base, connect_args_for, normalize_database_url  # noqa: E402
from app._database import models  # noqa: E402,F401 - populates Base.metadata
from app._database import rls  # noqa: E402

VARIABLE = "SCHEMA_CHECK_URL"
"""The environment variable holding the database URL to check."""

#: Fewer tables than this in the models means the import above stopped populating
#: the metadata. Zero tables would mean zero comparisons, and a check that makes no
#: comparisons passes while knowing nothing. migrations.py records this exact
#: failure for ensure_indexes.
MIN_MODEL_TABLES = 26

#: Fewer tables than this in the database means the credential cannot see the
#: schema, or it is the wrong database. Every table would then read as missing --
#: which fails loudly, but as a misleading list rather than the real cause.
MIN_LIVE_TABLES = 20


def rls_state(engine) -> dict | None:
    """Return which functions exist and how far row security is switched on.

    Args:
        engine: Engine for the database checked.

    Returns:
        The function names in schema `public`, how many tables have row security on,
        and whether the app role exists; None on SQLite.
    """
    if engine.dialect.name != "postgresql":
        return None
    with engine.connect() as conn:
        functions = set(conn.execute(text(
            "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public'"
        )).scalars())
        protected = conn.execute(text(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity"
        )).scalar()
        role_exists = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": rls.APP_ROLE}
        ).scalar() is not None
    return {"functions": functions, "protected": protected, "role_exists": role_exists}


def main() -> int:
    """Run the gate against `SCHEMA_CHECK_URL` and print the report.

    Tables in the database that no model builds, and the row-security state, are
    reported but never fail the gate.

    Returns:
        0 when every table, column and definer function is present; 1 when any is
        missing, with the fix printed; 2 when the URL is unset, the models or the
        database show too few tables, or the connection fails.
    """
    # Line-buffered, so in a CI log the report reads in order rather than every
    # stderr line arriving before the stdout it follows.
    sys.stdout.reconfigure(line_buffering=True)

    raw = os.environ.get(VARIABLE, "").strip()
    if not raw:
        print(f"{VARIABLE} is not set", file=sys.stderr)
        return 2

    url = normalize_database_url(raw)
    where = make_url(url).render_as_string(hide_password=True)

    expected = {name: table for name, table in Base.metadata.tables.items()}
    if len(expected) < MIN_MODEL_TABLES:
        print(
            f"Only {len(expected)} tables in the models (expected at least "
            f"{MIN_MODEL_TABLES}). The models import is not populating the metadata, "
            f"so this check would compare nothing.",
            file=sys.stderr,
        )
        return 2

    engine = create_engine(url, connect_args=connect_args_for(url), poolclass=NullPool)
    state = None
    try:
        try:
            inspector = inspect(engine)
            live_tables = set(inspector.get_table_names())
        except OperationalError as exc:
            # Could not connect, so nothing is known about the schema either way.
            # Exit 2, not 1: 1 means "a column is missing, apply the schema", and
            # sending someone to run a migration over a bad password is worse than
            # no message at all. The driver's last line carries the actual reason.
            reason = str(exc.orig).strip().splitlines()[-1] if exc.orig else str(exc)
            print(f"Could not connect to {where}:\n  {reason}", file=sys.stderr)
            print(
                "\nThis is the credential or the network, not the schema. Check the "
                f"{VARIABLE} secret: session pooler port 5432, and a username of the "
                "form <role>.<project-ref>.",
                file=sys.stderr,
            )
            return 2

        if len(live_tables) < MIN_LIVE_TABLES:
            print(
                f"{where} shows only {len(live_tables)} tables (expected at least "
                f"{MIN_LIVE_TABLES}). Wrong database, or a role that cannot see the "
                f"schema -- not a missing migration.",
                file=sys.stderr,
            )
            return 2

        missing: list[str] = []
        for name, table in sorted(expected.items()):
            if name not in live_tables:
                missing.append(f"{name}  (whole table)")
                continue
            present = {column["name"] for column in inspector.get_columns(name)}
            missing.extend(
                f"{name}.{column.name}"
                for column in table.columns
                if column.name not in present
            )

        # The row-level security functions. The API calls them to sign anyone
        # in, so new code against a database without them locks every user
        # out -- the same failure as a missing column, and the same fix.
        state = rls_state(engine)
        if state is not None:
            missing.extend(
                f"function {name}()" for name in rls.FUNCTIONS if name not in state["functions"]
            )
    finally:
        engine.dispose()

    print(f"Checked {len(expected)} tables against {where}")
    # Informational only: whether isolation is switched on is a decision made
    # by pointing the API at the app role, not something a deploy should gate.
    if state is not None:
        print(
            f"Row-level security: on for {state['protected']} of {len(expected)} tables; "
            f"role {rls.APP_ROLE} {'exists' if state['role_exists'] else 'does not exist'}"
        )

    # Reported, never failed on. A table production has and the models do not is
    # usually a feature removed without dropping its data -- a decision, not an
    # error (shipping.md, step 18). This counts them on every deploy for free,
    # where before they were found by someone counting by hand.
    extra = sorted(live_tables - set(expected))
    if extra:
        print(f"Tables in the database that no model builds: {', '.join(extra)}")

    if missing:
        print("\nMISSING -- this code will 500 against this database:", file=sys.stderr)
        for item in missing:
            print(f"  {item}", file=sys.stderr)
        print(
            "\nApply the schema first, then re-run the deploy:\n"
            "  cd Application/backend\n"
            "  set -a; source ../.env; set +a\n"
            '  DATABASE_URL="$SUPABASE_DATABASE_URL" python -m app._database.schema',
            file=sys.stderr,
        )
        return 1

    print("Every table and column this code selects is present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
