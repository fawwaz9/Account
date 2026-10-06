"""The usage report: right numbers, aggregates only, and it cannot write.

Run as a subprocess against a throwaway SQLite file, like the schema gate's
tests: the script points DATABASE_URL somewhere harmless at import, and
importing it here would leave that behind for every later test.
"""
import importlib.util
import os
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import sessionmaker

from app._database.models import Base, SurveyResponseModel, SyllabusParseModel, UsageEventModel, UserModel
from tests.conftest import TEST_DATABASE_URL, TESTING_SQLITE

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "usage_report.py"


def run(url):
    env = {k: v for k, v in os.environ.items() if k != "USAGE_REPORT_URL"}
    env["USAGE_REPORT_URL"] = url
    return subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True,
                          text=True, timeout=60)


@pytest.fixture
def usage_db(tmp_path):
    url = f"sqlite:///{tmp_path / 'usage.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    week = date.today() - timedelta(days=date.today().weekday())
    signup = datetime.combine(week, datetime.min.time()) + timedelta(hours=9)
    people = []
    for n in range(3):
        person = UserModel(id=uuid.uuid4(), name=f"Secret Name {n}", email=f"secret{n}@example.com",
                           email_verified=True, created_at=signup)
        session.add(person)
        people.append(person)
    session.flush()

    def use(person, kind, module, minutes_after=10):
        session.add(UsageEventModel(id=uuid.uuid4(), user_id=person.id, day=week, kind=kind,
                                    module=module, count=1,
                                    first_at=signup + timedelta(minutes=minutes_after),
                                    last_at=signup + timedelta(minutes=minutes_after)))

    use(people[0], "visit", "grades")
    use(people[0], "visit", "budget")             # two rooms: counts for the universe test
    use(people[0], "create", "grades", minutes_after=3)
    use(people[1], "visit", "dashboard")          # active, but no room
    use(people[1], "create", "tasks", minutes_after=30)
    # Two rooms, but both opened from a notification: the loose universe test
    # counts them, the vision's stricter one (one room unprompted) does not.
    use(people[2], "prompted_visit", "tasks")
    use(people[2], "prompted_visit", "calendar")
    use(people[2], "prompted_visit", "budget")    # sent there by a notification: not "without prompting"
    session.add(SurveyResponseModel(id=uuid.uuid4(), user_id=people[0].id,
                                    question="disappointment", answer="very"))
    session.add(SurveyResponseModel(id=uuid.uuid4(), user_id=people[1].id,
                                    question="disappointment", answer="dismissed"))

    def parse(person, minutes_to_confirm, total=None, changed=None):
        read = signup + timedelta(hours=1)
        session.add(SyllabusParseModel(
            id=uuid.uuid4(), user_id=person.id, provider="openai", model="m", result={},
            created_at=read, fields_total=total, fields_changed=changed,
            applied_at=None if minutes_to_confirm is None else read + timedelta(minutes=minutes_to_confirm)))

    parse(people[0], 3, total=10, changed=0)    # confirmed untouched, inside five minutes
    parse(people[1], 8, total=10, changed=2)    # two fields corrected, over five
    parse(people[1], 4)                          # added to a course: timed, no field counts
    parse(people[2], None)                       # read, never confirmed
    session.commit()
    identities = [(p.id, p.email, p.name) for p in people]
    session.close()
    engine.dispose()
    return url, identities


def test_the_numbers(usage_db):
    url, _ = usage_db
    result = run(url)
    assert result.returncode == 0, result.stderr
    this_week = [l for l in result.stdout.splitlines()
                 if l.strip().startswith((date.today() - timedelta(days=date.today().weekday())).isoformat())]
    assert this_week, result.stdout
    # new 3 | active 3 | two rooms 2 | two rooms, one unprompted 1 | back - | money room unprompted 1
    # (people[0] opened Budget on their own; people[2] only from a notification)
    assert [c.strip() for c in this_week[0].split("|")][1:7] == ["3", "3", "2", "1", "-", "1"]
    assert "3 of 4 read were confirmed; median 4.0 min; under 5 min: 2" in result.stdout
    assert "confirmed with nothing changed: 1 of 2; fields changed in review: 2 of 20" in result.stdout
    assert "very 1 | somewhat 0 | not 0 | declined to answer 1" in result.stdout
    assert "median 16 min across 2 accounts; under 5 min: 1" in result.stdout
    assert "signed up, nothing created yet: 1" in result.stdout
    assert "sinking_funds" in result.stdout and "<- unused" in result.stdout


def test_it_prints_nothing_that_identifies_anyone(usage_db):
    url, people = usage_db
    out = run(url).stdout
    for person_id, email, name in people:
        assert str(person_id) not in out and person_id.hex not in out
        assert email not in out and name not in out
    assert "secret" not in out.lower()


def test_it_opens_sqlite_read_only(usage_db):
    url, _ = usage_db
    spec = importlib.util.spec_from_file_location("usage_report_under_test", SCRIPT)
    saved = os.environ.get("DATABASE_URL")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        if saved is not None:
            os.environ["DATABASE_URL"] = saved
    engine = module.read_only_engine(url)
    try:
        with pytest.raises(OperationalError, match="readonly"):
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM users"))
    finally:
        engine.dispose()


@pytest.mark.skipif(TESTING_SQLITE, reason="needs Postgres")
def test_it_opens_postgres_read_only():
    spec = importlib.util.spec_from_file_location("usage_report_under_test_pg", SCRIPT)
    saved = os.environ.get("DATABASE_URL")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        if saved is not None:
            os.environ["DATABASE_URL"] = saved
    engine = module.read_only_engine(TEST_DATABASE_URL)
    try:
        with pytest.raises(DBAPIError, match="read-only"):
            with engine.begin() as conn:
                conn.execute(text("CREATE TEMP TABLE should_fail (id int)"))
    finally:
        engine.dispose()
