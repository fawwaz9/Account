"""Phase 0 analytics: the numbers the vision's phase gates are written in.

    USAGE_REPORT_URL=postgresql://... python scripts/usage_report.py [--weeks 8]

Prints aggregate counts and nothing else: no ids, names, emails or anything
typed by a user. It reads per-user usage counters to compute those numbers,
which is why it is a script the owner runs rather than an endpoint -- the API
never reads across users, and under row-level security it cannot.

**Read-only, enforced, not promised.** On Postgres every transaction is
declared READ ONLY, so a write would be refused by the server; on SQLite the
file is opened in read-only mode. Point it at a copy if you like, but it cannot
change the database it is pointed at.

What it reports, and which gate each answers (account-vision.md §8, §11):

* **Accounts** -- total, and new per week where the signup time is known.
* **Weekly actives** -- anyone who opened or added anything that week.
* **Universe test** -- people who used two or more rooms in one week. The rooms
  are grades, calendar, tasks, jobs and budget; the dashboard and settings are
  not rooms.
* **Retention** -- of last week's actives, how many came back this week.
* **Module adoption** -- distinct people per room over the last four weeks, and
  rows per table, which is how a zero-row feature gets noticed.
* **Time to first value** -- from signup to the first thing created, for
  accounts made after signup times started being recorded.
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
ROOMS = ("grades", "calendar", "tasks", "jobs", "budget")


def read_only_engine(raw: str):
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
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")

    return engine


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def collect(engine) -> dict:
    users = models.UserModel.__table__
    usage = models.UsageEventModel.__table__
    with engine.connect() as conn:
        user_rows = conn.execute(select(users.c.id, users.c.created_at, users.c.deleted_at)).all()
        usage_rows = conn.execute(
            select(usage.c.user_id, usage.c.day, usage.c.kind, usage.c.module, usage.c.first_at)
        ).all()
        table_counts = {
            table.name: conn.execute(select(func.count()).select_from(table)).scalar()
            for table in Base.metadata.sorted_tables
        }
    return {"users": user_rows, "usage": usage_rows, "tables": table_counts}


def report(data: dict, weeks: int, today: date) -> list[str]:
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
    adoption = defaultdict(set)        # room -> people, last four weeks
    creates = defaultdict(int)         # room -> creates, last four weeks
    first_create = {}
    recent = this_week - timedelta(weeks=3)
    for row in data["usage"]:
        week = monday(row.day)
        active[week].add(row.user_id)
        if row.module in ROOMS:
            rooms[week][row.user_id].add(row.module)
            if week >= recent:
                adoption[row.module].add(row.user_id)
        if row.kind == "create":
            if week >= recent:
                creates[row.module] += 1
            seen = first_create.get(row.user_id)
            if seen is None or row.first_at < seen:
                first_create[row.user_id] = row.first_at

    out.append("")
    out.append("WEEKLY  (week of | new accounts | active | 2+ rooms | back from last week)")
    previous = None
    for week in week_starts:
        people = active.get(week, set())
        universe = sum(1 for r in rooms.get(week, {}).values() if len(r) >= 2)
        back = f"{len(people & previous)}/{len(previous)}" if previous else "-"
        out.append(f"  {week.isoformat()} | {new_by_week.get(week, 0):>3} | {len(people):>3} | "
                   f"{universe:>3} | {back}")
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
    out.append("ROWS PER TABLE  (a zero is a feature nobody has used)")
    for name, count in sorted(data["tables"].items()):
        flag = "   <- unused" if count == 0 else ""
        out.append(f"  {name:<32} {count}{flag}")
    return out


def main() -> int:
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
