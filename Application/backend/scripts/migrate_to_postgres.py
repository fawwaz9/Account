"""Copy every row from a SQLite database into an empty Postgres one.

Run it against a **copy** of `data/app.db`, made with `VACUUM INTO` rather than
`cp`: SQLite in WAL mode keeps recent writes in a sidecar file, so a plain copy
of the main file can be missing whatever has not been checkpointed yet.
`VACUUM INTO` produces a consistent single file whatever the writer is doing.
This script refuses to open the real database at all.

**Why through SQLAlchemy rather than a SQL dump.** `sqlalchemy.types.Uuid`
stores as `CHAR(32)` on SQLite and as a native `uuid` on Postgres; `Boolean` is
`0`/`1` against `false`/`true`; `JSON` is text against `jsonb`. Reading and
writing through the same metadata means each column's type converts itself on
the way through. A dump carries the SQLite spelling across and produces either a
type error or -- far worse -- valid-looking wrong data. D1.4.

Usage:

    python -m scripts.migrate_to_postgres \\
        --source /tmp/app-copy.db \\
        --target-env SUPABASE_DATABASE_URL
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app._database.db import (  # noqa: E402
    DEFAULT_DB_PATH,
    connect_args_for,
    engine_kwargs_for,
    normalize_database_url,
)
from app._database.migrations import ensure_indexes  # noqa: E402
from app._database.models import Base  # noqa: E402

#: Rows sent per round trip. The whole database is a few hundred rows today, but
#: this runs over a network to a pooler, so an unbounded executemany would be one
#: enormous statement rather than several small ones.
BATCH = 500


class Refused(Exception):
    """A guard said no. The message is the whole explanation."""


def check_source(path: Path) -> Path:
    """The one rule: never the live database.

    A migration reads, so in principle pointing it at the original is harmless.
    In practice it is one flag away from a script that also writes, the file is
    open under a WAL, and a copy costs a second. The guard compares resolved
    paths so a symlink or a relative path cannot walk around it.
    """
    path = path.resolve()
    if not path.exists():
        raise Refused(f"{path} does not exist")
    if path == DEFAULT_DB_PATH.resolve():
        raise Refused(
            f"{path} is the live database.\n"
            "Make a copy first -- and with VACUUM INTO, not cp:\n"
            f"  sqlite3 {DEFAULT_DB_PATH} \"VACUUM INTO '/tmp/app-copy.db'\"\n"
            "then point --source at the copy."
        )
    return path


def canonical(value) -> str:
    """One spelling for a value, whichever database it came out of.

    Both sides are read through the same metadata, so the types arrive already
    converted -- a `uuid.UUID` either way, a `date` either way. What is left is
    the handful of places two equal values still print differently: a dict whose
    keys came back in another order, and a float that is 5 on one side and 5.0
    on the other.
    """
    import json

    if value is None:
        return "\x00"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    if isinstance(value, float):
        # 12 places is far beyond any money value here and short of the noise
        # floor where the two drivers can disagree on the last bit.
        return f"{value:.12g}"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def fingerprint(connection, table) -> str:
    """A hash of every value in a table, order-independent.

    Counting rows proves a table is not missing. It says nothing about whether a
    boolean arrived as the right boolean, a UUID kept its bytes, or a JSON blob
    survived the trip -- and those are exactly the failures a type conversion
    produces. Each row is hashed on its own and the digests are combined by XOR,
    so the two sides need no shared ORDER BY and no stable primary-key ordering.
    """
    import hashlib

    columns = [c.name for c in table.columns]
    total = 0
    for row in connection.execute(select(table)).mappings():
        line = "\x1f".join(canonical(row[name]) for name in columns)
        total ^= int.from_bytes(hashlib.blake2b(line.encode(), digest_size=16).digest(), "big")
    return f"{total:032x}"


def counts(connection) -> dict[str, int]:
    """Rows per table, for the same metadata on either side."""
    return {
        table.name: connection.execute(select(func.count()).select_from(table)).scalar_one()
        for table in Base.metadata.sorted_tables
    }


def copy_table(source, target, table) -> int:
    """Every row of one table, in batches, types converted by the metadata."""
    rows = source.execute(select(table)).mappings().all()
    if not rows:
        return 0
    for start in range(0, len(rows), BATCH):
        target.execute(table.insert(), [dict(row) for row in rows[start : start + BATCH]])
    return len(rows)


def resettable_sequences() -> list[tuple[str, str]]:
    """Integer primary keys that Postgres backs with a sequence.

    Every other table keys on a UUID the application generates, so this is a
    list of one today -- `course_category_weights.id`. It is derived rather than
    written down because the consequence of missing a future one is invisible
    until somebody writes a row: inserting explicit ids does not advance the
    sequence, so the next insert asks for id 1, collides, and keeps colliding.
    The migration would look perfect and the table would be permanently
    unwritable.
    """
    found = []
    for table in Base.metadata.sorted_tables:
        for column in table.primary_key.columns:
            if isinstance(column.type, (sa.Integer, sa.BigInteger)) and column.autoincrement is not False:
                found.append((table.name, column.name))
    return found


def reset_sequences(target) -> list[str]:
    done = []
    for table_name, column in resettable_sequences():
        sequence = target.execute(
            sa.text("SELECT pg_get_serial_sequence(:t, :c)"), {"t": table_name, "c": column}
        ).scalar()
        if sequence is None:
            # No sequence behind it -- nothing to advance.
            continue
        target.execute(
            sa.text(
                f"SELECT setval(:seq, COALESCE((SELECT MAX({column}) FROM {table_name}), 0) + 1, false)"
            ),
            {"seq": sequence},
        )
        done.append(f"{table_name}.{column}")
    return done


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="a COPY of data/app.db")
    parser.add_argument("--target-env", default="SUPABASE_DATABASE_URL",
                        help="environment variable holding the Postgres URL")
    parser.add_argument("--target", help="the Postgres URL directly, instead of --target-env")
    parser.add_argument("--replace", action="store_true",
                        help="proceed even though the target already holds rows (drops them)")
    args = parser.parse_args()

    try:
        source_path = check_source(args.source)
    except Refused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2

    target_url = args.target or os.getenv(args.target_env)
    if not target_url:
        print(f"refused: {args.target_env} is not set, and --target was not given", file=sys.stderr)
        return 2
    target_url = normalize_database_url(target_url)
    if make_url(target_url).get_backend_name() == "sqlite":
        print("refused: the target is SQLite. This moves data *to* Postgres.", file=sys.stderr)
        return 2

    source_engine = create_engine(f"sqlite:///{source_path}",
                                  connect_args=connect_args_for("sqlite://"))
    target_engine = create_engine(target_url, connect_args=connect_args_for(target_url),
                                  **engine_kwargs_for(target_url))

    print(f"source  {source_path}")
    print(f"target  {make_url(target_url).host}:{make_url(target_url).port}"
          f"/{make_url(target_url).database}\n")

    try:
        with source_engine.connect() as source:
            before = counts(source)
        total = sum(before.values())
        print(f"{total} rows across {sum(1 for n in before.values() if n)} non-empty tables\n")

        # The schema the application would build, so the move cannot invent a
        # shape the app does not expect.
        #
        # `ensure_schema()` is deliberately NOT called. It takes no bind and
        # operates on the application's own engine, so calling it here would
        # issue DDL against the local SQLite database rather than the target.
        # It would also have nothing to do: it only adds columns that
        # `create_all` did not, and on a database create_all just built there
        # are none. That is D1.3's argument for deferring Alembic, and it is why
        # this move needs no migration framework.
        Base.metadata.create_all(bind=target_engine)
        ensure_indexes(bind=target_engine)

        with target_engine.connect() as target:
            existing = counts(target)
        occupied = {name: n for name, n in existing.items() if n}
        if occupied and not args.replace:
            print("refused: the target is not empty.", file=sys.stderr)
            for name, n in sorted(occupied.items()):
                print(f"  {name}: {n} rows", file=sys.stderr)
            print("\nPass --replace to delete these and copy over them.", file=sys.stderr)
            return 3

        # One transaction for the whole move. A migration that half-succeeded
        # would leave a database that is neither the old one nor the new one,
        # and no way to tell which tables made it.
        with target_engine.begin() as target:
            if occupied:
                for table in reversed(Base.metadata.sorted_tables):
                    target.execute(table.delete())

            copied = {}
            with source_engine.connect() as source:
                # Parents first. sorted_tables is derived from the declared
                # foreign keys, so adding a table later orders itself; a written
                # list would not, and the failure would be an FK violation
                # halfway through a move.
                for table in Base.metadata.sorted_tables:
                    copied[table.name] = copy_table(source, target, table)

            sequences = reset_sequences(target)

        with target_engine.connect() as target:
            after = counts(target)
            target_prints = {t.name: fingerprint(target, t) for t in Base.metadata.sorted_tables}
        with source_engine.connect() as source:
            source_prints = {t.name: fingerprint(source, t) for t in Base.metadata.sorted_tables}

    finally:
        source_engine.dispose()
        target_engine.dispose()

    # ---- verification, which is the point of the exercise ----
    width = max(len(name) for name in before)
    mismatched = []
    print(f"{'table'.ljust(width)}  {'sqlite':>7}  {'postgres':>8}  values")
    for name in sorted(before):
        src, dst = before[name], after[name]
        if src == 0 and dst == 0:
            continue
        same_count = src == dst
        same_values = source_prints[name] == target_prints[name]
        if not (same_count and same_values):
            mismatched.append(name)
        verdict = "match" if same_values else "DIFFER"
        flag = "" if same_count else "   <-- COUNT MISMATCH"
        print(f"{name.ljust(width)}  {src:>7}  {dst:>8}  {verdict}{flag}")

    print(f"\n{sum(after.values())} rows copied of {total}")
    if sequences:
        print(f"sequences advanced past the copied ids: {', '.join(sequences)}")

    if mismatched:
        print(f"\nFAILED: {len(mismatched)} table(s) disagree: {', '.join(mismatched)}", file=sys.stderr)
        return 1

    print("\nEvery table matches, by row count and by the value of every column.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
