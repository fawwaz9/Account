"""The deploy's schema gate: refuses code that needs a column the database lacks.

Run as a subprocess, not imported. The script points DATABASE_URL somewhere
harmless at import, so that whatever environment calls it can never reach the
real data/app.db through the module-level engine -- and importing it here would
leave that override behind for every test that runs afterwards.

Each case builds its own throwaway SQLite file. Nothing here touches a configured
database.
"""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

from app._database.db import Base

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_schema_conformance.py"


def run_check(url: str | None):
    env = {k: v for k, v in os.environ.items() if k != "SCHEMA_CHECK_URL"}
    if url is not None:
        env["SCHEMA_CHECK_URL"] = url
    return subprocess.run(
        [sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60
    )


def full_schema(path: Path) -> str:
    url = f"sqlite:///{path}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    return url


def test_a_database_with_every_table_and_column_passes(tmp_path):
    result = run_check(full_schema(tmp_path / "full.db"))

    assert result.returncode == 0, result.stderr
    assert "Every table and column this code selects is present." in result.stdout


def test_a_missing_column_fails_and_names_it(tmp_path):
    url = full_schema(tmp_path / "missing.db")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE tasks DROP COLUMN estimated_minutes"))
    engine.dispose()

    result = run_check(url)

    assert result.returncode == 1
    assert "tasks.estimated_minutes" in result.stderr
    # The fix is printed with the failure, so nobody has to go and find it.
    assert "python -m app._database.schema" in result.stderr


def test_a_missing_table_fails_and_names_it(tmp_path):
    url = full_schema(tmp_path / "no_table.db")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE account_month_values"))
    engine.dispose()

    result = run_check(url)

    assert result.returncode == 1
    assert "account_month_values  (whole table)" in result.stderr


def test_an_extra_table_is_reported_but_does_not_fail(tmp_path):
    # A removed feature's table left in place is a decision, not an error.
    url = full_schema(tmp_path / "extra.db")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE category_budgets (id INTEGER PRIMARY KEY)"))
    engine.dispose()

    result = run_check(url)

    assert result.returncode == 0, result.stderr
    assert "no model builds: category_budgets" in result.stdout


def test_an_empty_database_is_refused_as_meaningless_not_reported_as_missing(tmp_path):
    # Every table reading as missing would be a loud failure with the wrong cause.
    result = run_check(f"sqlite:///{tmp_path / 'empty.db'}")

    assert result.returncode == 2
    assert "Wrong database" in result.stderr


def test_no_url_is_refused(tmp_path):
    result = run_check(None)

    assert result.returncode == 2
    assert "SCHEMA_CHECK_URL is not set" in result.stderr


def test_a_connection_failure_is_not_reported_as_a_missing_schema(tmp_path):
    # Exit 1 sends someone to run a migration. A bad password must not.
    result = run_check("postgresql://nobody:wrong@127.0.0.1:1/none")

    assert result.returncode == 2
    assert "Could not connect" in result.stderr
    assert "not the schema" in result.stderr
    assert "Traceback" not in result.stderr
