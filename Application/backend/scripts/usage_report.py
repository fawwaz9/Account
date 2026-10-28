"""Print the phase-gate analytics as aggregate counts, read-only, for the owner to run.

    USAGE_REPORT_URL=postgresql://... python scripts/usage_report.py [--weeks 8]

Prints counts and nothing else: no ids, names, emails or anything a user typed. It
reads every user's usage counters, which is why it is an owner-run script and never
an endpoint. Read-only is enforced: every Postgres transaction is declared READ
ONLY, and a SQLite file is opened in read-only mode.

Reports accounts and new signups per week; weekly actives; the universe test (two
or more rooms in a week, and the strict form with at least one unprompted visit);
week-on-week retention; unprompted Budget use; room adoption and rows per table;
time from signup to first creation; the disappointment survey's answers; and
syllabus read-to-confirm times with the no-change rate. The rooms are grades,
calendar, tasks, jobs and budget.
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite://"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, event, func, select  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app._database import models  # noqa: E402
from app._database.db import Base, connect_args_for, normalize_database_url  # noqa: E402

VARIABLE = "USAGE_REPORT_URL"
"""The environment variable holding the database URL to report on."""
ROOMS = ("grades", "calendar", "tasks", "jobs", "budget")
"""The modules that count as rooms; the dashboard and settings do not."""


def read_only_engine(raw: str):
    """Return an engine that cannot write: read-only transactions, or a read-only file.

    Args:
        raw: The database URL from `USAGE_REPORT_URL`.

    Returns:
        An unpooled engine; on Postgres every transaction begins `READ ONLY`.

    Raises:
        SystemExit: If a SQLite URL names no file.
    """
    url = normalize_database_url(raw)
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite":
        path = parsed.database
        if not path or path == ":memory:":
            raise SystemExit("A SQLite report needs a file path.")
        engine = create_engine(f"sqlite:///file:{path}?mode=ro&uri=true", poolclass=NullPool)
        return engine

    engine = create_engine(url, connect_args=connect_args_for(url), poolclass=NullPool)

    @event.listens_for(engine, "begin")
    def _read_only(conn):
        """Declare each new transaction read-only."""
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")

    return engine


def monday(day: date) -> date:
    """Return the Monday of the week a date falls in.

    Args:
        day: Any date.

    Returns:
        The Monday on or before `day`.
    """
    return day - timedelta(days=day.weekday())


def collect(engine) -> dict:
    """Read the rows the report needs, across every user.

    Args:
        engine: The read-only engine.

    Returns:
        A dict of "users", "usage", "answers", "parses" and per-table row counts
        ("tables").
    """
    users = models.UserModel.__table__
    usage = models.UsageEventModel.__table__
    with engine.connect() as conn:
        user_rows = conn.execute(select(users.c.id, users.c.created_at, users.c.deleted_at)).all()
        usage_rows = conn.execute(
            select(usage.c.user_id, usage.c.day, usage.c.kind, usage.c.module, usage.c.first_at)
        ).all()
        survey = models.SurveyResponseModel.__table__
        answers = conn.execute(select(survey.c.question, survey.c.answer)).all()
        parses = models.SyllabusParseModel.__table__
        parse_rows = conn.execute(
            select(parses.c.created_at, parses.c.applied_at, parses.c.fields_total, parses.c.fields_changed)
        ).all()
        table_counts = {
            table.name: conn.execute(select(func.count()).select_from(table)).scalar()
            for table in Base.metadata.sorted_tables
        }
    return {"users": user_rows, "usage": usage_rows, "tables": table_counts, "answers": answers,
            "parses": parse_rows}


def report(data: dict, weeks: int, today: date) -> list[str]:
    """Return the report's lines from collected data.

    Args:
        data: What `collect` returned.
        weeks: How many weeks of weekly rows to show, ending with this week.
        today: The day the weeks are counted back from.

    Returns:
        The lines to print.
    """
    out: list[str] = []
    live = [u for u in data["users"] if u.deleted_at is None]
    this_week = monday(today)
    week_starts = [this_week - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]

    out.append("ACCOUNTS")
    out.append(f"  total {len(live)} (plus {len(data['users']) - len(live)} pending deletion)")
    known = [u for u in live if u.created_at is not None]
    out.append(f"  signup time known for {len(known)}")
    new_by_week = defaultdict(int)
    for u in known:
        new_by_week[monday(u.created_at.date())] += 1

    active = defaultdict(set)          # week -> people
    rooms = defaultdict(lambda: defaultdict(set))  # week -> person -> rooms
    unprompted = defaultdict(lambda: defaultdict(set))  # week -> person -> rooms visited unprompted
    adoption = defaultdict(set)        # room -> people, last four weeks
    creates = defaultdict(int)         # room -> creates, last four weeks
    first_create = {}
    recent = this_week - timedelta(weeks=3)
    for row in data["usage"]:
        week = monday(row.day)
        active[week].add(row.user_id)
        if row.module in ROOMS:
            rooms[week][row.user_id].add(row.module)
            if row.kind == "visit":
                unprompted[week][row.user_id].add(row.module)
            if week >= recent:
                adoption[row.module].add(row.user_id)
        if row.kind == "create":
            if week >= recent:
                creates[row.module] += 1
            seen = first_create.get(row.user_id)
            if seen is None or row.first_at < seen:
                first_create[row.user_id] = row.first_at

    out.append("")
    out.append("WEEKLY  (week of | new accounts | active | 2+ rooms | 2+ rooms, one unprompted | back from last week"
               " | money room, unprompted)")
    previous = None
    for week in week_starts:
        people = active.get(week, set())
        week_rooms = rooms.get(week, {})
        universe = sum(1 for r in week_rooms.values() if len(r) >= 2)
        strict = sum(
            1 for person, r in week_rooms.items()
            if len(r) >= 2 and unprompted.get(week, {}).get(person)
        )
        back = f"{len(people & previous)}/{len(previous)}" if previous else "-"
        money = sum(1 for visited in unprompted.get(week, {}).values() if "budget" in visited)
        out.append(f"  {week.isoformat()} | {new_by_week.get(week, 0):>3} | {len(people):>3} | "
                   f"{universe:>3} | {strict:>3} | {back} | {money:>3}")
        previous = people

    out.append("")
    out.append("ROOMS, last four weeks  (people | things created)")
    for room in ROOMS:
        out.append(f"  {room:<9} {len(adoption.get(room, set())):>3} | {creates.get(room, 0)}")

    out.append("")
    out.append("TIME TO FIRST VALUE  (signup to first thing created)")
    minutes = [
        (first_create[u.id] - u.created_at).total_seconds() / 60
        for u in known if u.id in first_create and first_create[u.id] >= u.created_at
    ]
    if minutes:
        out.append(f"  median {statistics.median(minutes):.0f} min across {len(minutes)} accounts; "
                   f"under 5 min: {sum(1 for m in minutes if m < 5)}")
    else:
        out.append("  no accounts with both a signup time and a first creation yet")
    out.append(f"  signed up, nothing created yet: {sum(1 for u in known if u.id not in first_create)}")

    out.append("")
    out.append("WOULD YOU BE DISAPPOINTED WITHOUT IT  (Phase 1 gate: 3 or more \"very\")")
    asked = [row.answer for row in data.get("answers", []) if row.question == "disappointment"]
    if asked:
        counts = {answer: asked.count(answer) for answer in ("very", "somewhat", "not", "dismissed")}
        out.append(f"  very {counts['very']} | somewhat {counts['somewhat']} | not {counts['not']} | "
                   f"declined to answer {counts['dismissed']}")
    else:
        out.append("  nobody has been asked yet (people are asked after 7 days of use)")

    out.append("")
    out.append("SYLLABUS TO TERM  (read to confirmed, review included; Phase 1 gate: under 5 min)")
    parses = data.get("parses", [])
    confirmed = [row for row in parses if row.applied_at is not None and row.applied_at >= row.created_at]
    if confirmed:
        taken = [(row.applied_at - row.created_at).total_seconds() / 60 for row in confirmed]
        out.append(f"  {len(confirmed)} of {len(parses)} read were confirmed; median "
                   f"{statistics.median(taken):.1f} min; under 5 min: {sum(1 for m in taken if m < 5)}")
        counted = [row for row in confirmed if row.fields_total]
        if counted:
            untouched = sum(1 for row in counted if not row.fields_changed)
            changed = sum(row.fields_changed or 0 for row in counted)
            total = sum(row.fields_total for row in counted)
            out.append(f"  confirmed with nothing changed: {untouched} of {len(counted)}; "
                       f"fields changed in review: {changed} of {total}")
    else:
        out.append(f"  none confirmed yet ({len(parses)} read)")

    out.append("")
    out.append("ROWS PER TABLE  (a zero is a feature nobody has used)")
    for name, count in sorted(data["tables"].items()):
        flag = "   <- unused" if count == 0 else ""
        out.append(f"  {name:<32} {count}{flag}")
    return out


def main() -> int:
    """Print the report for `USAGE_REPORT_URL`.

    Returns:
        0 after printing; 2 when `USAGE_REPORT_URL` is unset.
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--weeks", type=int, default=8)
    args = parser.parse_args()
    raw = os.environ.get(VARIABLE, "").strip()
    if not raw:
        print(f"{VARIABLE} is not set", file=sys.stderr)
        return 2
    engine = read_only_engine(raw)
    try:
        data = collect(engine)
    finally:
        engine.dispose()
    print("\n".join(report(data, args.weeks, date.today())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
