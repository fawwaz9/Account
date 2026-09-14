"""The one-time move from SQLite to Postgres, and the guards on it.

The script itself was verified end to end against a `VACUUM INTO` copy of the
real database into a throwaway Postgres 16: 588 rows, every table matching by
count and by the value of every column. What is tested here is the logic that
decides whether the move is *allowed* to run and whether it can tell a good
result from a bad one -- because those are what protect the real database, and
they are the parts a future edit could quietly break.
"""
import importlib.util
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

BACKEND = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location(
        "migrate_to_postgres", BACKEND / "scripts" / "migrate_to_postgres.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("migrate_to_postgres", module)
    spec.loader.exec_module(module)
    return module


migrate = load()


# ------------------------------------------------ never the live database --

def test_the_live_database_is_refused():
    """The rule from the incident that produced it.

    A migration only reads, so pointing it at the original is harmless today.
    It is also one flag away from a script that writes, the file is open under
    a WAL, and a copy costs a second.
    """
    from app._database.db import DEFAULT_DB_PATH

    if not DEFAULT_DB_PATH.exists():
        pytest.skip("no live database on this machine to guard")

    with pytest.raises(migrate.Refused) as refusal:
        migrate.check_source(DEFAULT_DB_PATH)

    assert "live database" in str(refusal.value)
    # The refusal has to carry the fix, not just the objection.
    assert "VACUUM INTO" in str(refusal.value)


def test_the_guard_compares_resolved_paths(tmp_path, monkeypatch):
    """Otherwise `../backend/data/app.db` or a symlink walks straight around it."""
    from app._database.db import DEFAULT_DB_PATH

    if not DEFAULT_DB_PATH.exists():
        pytest.skip("no live database on this machine to guard")

    link = tmp_path / "innocent-looking-copy.db"
    link.symlink_to(DEFAULT_DB_PATH)

    with pytest.raises(migrate.Refused):
        migrate.check_source(link)


def test_a_real_copy_is_allowed(tmp_path):
    copy = tmp_path / "app-copy.db"
    copy.write_bytes(b"")
    assert migrate.check_source(copy) == copy.resolve()


def test_a_source_that_is_not_there_is_refused(tmp_path):
    with pytest.raises(migrate.Refused, match="does not exist"):
        migrate.check_source(tmp_path / "nothing.db")


# --------------------------------------- telling a good result from a bad --

def test_two_equal_values_spelled_differently_still_compare_equal():
    """Both sides are read through the same metadata, so the types already
    match. What is left is where two *equal* values print differently."""
    assert migrate.canonical({"b": 1, "a": 2}) == migrate.canonical({"a": 2, "b": 1})
    assert migrate.canonical(5.0) == migrate.canonical(5)
    assert migrate.canonical(None) == migrate.canonical(None)


def test_values_that_differ_do_not_collide():
    """The other half. A canonical form that flattens everything compares equal
    to anything, which is a verification that always passes."""
    assert migrate.canonical(None) != migrate.canonical("")
    assert migrate.canonical(True) != migrate.canonical("true is a string")
    # A boolean column and an integer column never both feed the same value,
    # but keeping them distinct costs nothing and a collapsed NULL/0/False is
    # exactly the kind of thing a type conversion gets wrong.
    assert migrate.canonical(False) != migrate.canonical(0)
    assert migrate.canonical(False) != migrate.canonical(None)
    assert migrate.canonical(1.0) != migrate.canonical(1.0000000001)


def test_the_fingerprint_notices_one_changed_character():
    """The check that matters. Row counts are identical across a corrupted
    copy -- a value-level difference is the only thing that catches a bad type
    conversion, which is the failure this whole approach exists to prevent."""
    metadata = sa.MetaData()
    rows = sa.Table("rows", metadata,
                    sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("note", sa.String))

    def digest(values):
        engine = sa.create_engine("sqlite://")
        metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(rows.insert(), values)
        with engine.connect() as conn:
            return migrate.fingerprint(conn, rows)

    original = [{"id": 1, "note": "School Needs"}, {"id": 2, "note": "Rent"}]
    changed = [{"id": 1, "note": "School Needsx"}, {"id": 2, "note": "Rent"}]

    assert digest(original) == digest(original)
    assert digest(original) != digest(changed)


def test_the_fingerprint_does_not_depend_on_row_order():
    """Neither side is given an ORDER BY, and Postgres has no obligation to
    return rows in the order they were inserted."""
    metadata = sa.MetaData()
    rows = sa.Table("rows", metadata,
                    sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("note", sa.String))

    def digest(values):
        engine = sa.create_engine("sqlite://")
        metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(rows.insert(), values)
        with engine.connect() as conn:
            return migrate.fingerprint(conn, rows)

    forwards = [{"id": 1, "note": "a"}, {"id": 2, "note": "b"}, {"id": 3, "note": "c"}]
    assert digest(forwards) == digest(list(reversed(forwards)))


# ------------------------------------------------------------- sequences --

def test_the_integer_primary_key_is_found():
    """Derived from the models rather than written down.

    Inserting explicit ids does not advance a Postgres sequence, so a table
    missed here accepts the migration and then rejects every future insert with
    a duplicate key -- forever, and invisibly until someone writes a row.
    """
    found = dict(migrate.resettable_sequences())
    assert found.get("course_category_weights") == "id"


def test_uuid_keyed_tables_need_no_sequence():
    """Everything else keys on a UUID the application generates."""
    found = dict(migrate.resettable_sequences())
    for table in ("users", "courses", "transactions", "grades", "accounts"):
        assert table not in found
