"""Recompute every course's stored average under the even-share rule (D29), once.

    export RECOMPUTE_URL=postgresql://...
    python scripts/recompute_averages.py            # list what would change
    python scripts/recompute_averages.py --apply    # write it

D29 changed how a category is averaged: every item counts the same unless its
category is split, where it used to count by its points. `courses.average` is
stored, and readers never recompute it, so every course keeps its old figure until
one of its grades is next saved. This brings them all over at once.

The listing shows each course whose average moves, old to new, by course code,
term and the first eight characters of its id -- never whose it is. A course with
a recorded final grade is marked: its letter, GPA and year average come from that
final, so they don't move. Only `average` is written; a recorded projection
(`projected_before_final`) is history and is left as it was. Run the listing,
read it, then run --apply. It runs as the tables' owner, since the API's role sees
one user at a time.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite://"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, selectinload, sessionmaker  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app._database import rls  # noqa: E402
from app._database.db import connect_args_for, normalize_database_url  # noqa: E402
from app._database.models import CourseModel  # noqa: E402
from app.Grades.services.grade_service import course_grade  # noqa: E402

VARIABLE = "RECOMPUTE_URL"
"""The environment variable holding the database URL."""

#: A change smaller than this is rounding, not a change.
EPSILON = 0.005


def check_connection(session: Session) -> str | None:
    """Return why the connection can't recompute every course, or None when it can.

    Args:
        session: An open session.

    Returns:
        A reason to stop, or None.
    """
    if session.bind.dialect.name != "postgresql":
        return None
    who = session.execute(text("SELECT current_user")).scalar()
    if who == rls.APP_ROLE:
        return f"Connected as {rls.APP_ROLE}, the API's role, which sees one user at a time. Run as the tables' owner."
    return None


def changes(session: Session) -> list[tuple[CourseModel, float, float]]:
    """Return every course whose stored average differs from a fresh one.

    Args:
        session: An open session.

    Returns:
        (course, stored, fresh), ordered by year, term and code.
    """
    courses = (
        session.query(CourseModel)
        .options(
            selectinload(CourseModel.grades),
            selectinload(CourseModel.category_weight_rows),
            selectinload(CourseModel.grading_schemes),
        )
        .order_by(CourseModel.year, CourseModel.semester, CourseModel.code)
        .all()
    )
    found = []
    for course in courses:
        stored = course.average or 0.0
        fresh = course_grade(course)
        if abs(fresh - stored) >= EPSILON:
            found.append((course, stored, fresh))
    return found


def listing(found: list[tuple[CourseModel, float, float]]) -> list[str]:
    """Return the lines that show what would change.

    Args:
        found: From `changes`.

    Returns:
        One line per course, then a count.
    """
    if not found:
        return ["Every stored average is already current. Nothing to change."]
    lines = []
    for course, stored, fresh in found:
        note = "  (final grade recorded: letter and GPA unchanged)" if course.final_grade and course.final_grade > 0 else ""
        lines.append(
            f"{str(course.id)[:8]}  {course.code:<12} year {course.year} {course.semester:<7} "
            f"{stored:6.2f} -> {fresh:6.2f}{note}"
        )
    lines.append(f"{len(found)} course average(s) would change.")
    return lines


def open_session(raw: str) -> Session:
    """Return a session on the given database URL, with no connection pooling.

    Args:
        raw: A database URL as pasted; normalised first.

    Returns:
        A new session; the caller closes it.
    """
    url = normalize_database_url(raw)
    engine = create_engine(url, connect_args=connect_args_for(url), poolclass=NullPool)
    return sessionmaker(bind=engine)()


def main(argv: list[str] | None = None) -> int:
    """List the averages that would change, or write them with --apply.

    Args:
        argv: Arguments instead of `sys.argv`, for tests.

    Returns:
        0 on success; 2 when `RECOMPUTE_URL` is unset or the connection is refused.
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="write the new averages")
    args = parser.parse_args(argv)
    raw = os.environ.get(VARIABLE, "").strip()
    if not raw:
        print(f"{VARIABLE} is not set", file=sys.stderr)
        return 2
    session = open_session(raw)
    try:
        refused = check_connection(session)
        if refused:
            print(refused, file=sys.stderr)
            return 2
        found = changes(session)
        print("\n".join(listing(found)))
        if args.apply and found:
            for course, _, fresh in found:
                course.average = fresh
            session.commit()
            print(f"Wrote {len(found)}.")
        elif found:
            print("Nothing written. Run again with --apply to write these.")
    finally:
        session.close()
        session.bind.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
