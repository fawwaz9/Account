"""Grade distributions shown (Phase 3 item 3, D11), on SQLite and on Postgres.

The promises: a course's counts are read only through the floor, only for terms
whose asking window has closed, only for the course key the caller's own course is
counted under, and the read function and its SQLite twin say the same.
"""
import re
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database import aggregates, rls
from app._database.db import get_db
from app._database.identity import act_as
from app._database.models import COHORT_FLOOR, COUNTED_AFTER_DAYS, CourseModel, GradeDistributionModel
from app.Auth.services.session_service import create_access_token
from app.Grades.services import class_figures_service as service
from app.Grades.services.term_review_service import ASK_UNTIL_DAYS
from conftest import make_user

TODAY = date.today()
#: Two years back: its window closed long ago, whatever day the suite runs.
CLOSED = f"{TODAY.year - 2}W1"
OLDER = f"{TODAY.year - 3}W2"
#: This year's Fall: it has not even ended, so its window is open.
OPEN = f"{TODAY.year}W1"


def student(db, name="Sam"):
    user = make_user(db, f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com")
    user.name = name
    db.commit()
    act_as(db, user.id)
    return user


def course(db, user, code="CPSC 221", final=0.0, average=0.0, **extra):
    row = CourseModel(id=uuid.uuid4(), user_id=user.id, code=code, name="Algorithms", semester="Fall",
                      year=2, credits=4.0, final_grade=final, average=average, **extra)
    db.add(row)
    db.commit()
    return row


def counts(db, key, term, bands):
    """Seed the sealed table as the recount would: {bucket: contributors}."""
    for bucket, n in bands.items():
        db.add(GradeDistributionModel(id=uuid.uuid4(), course_key=key, term_code=term, bucket=bucket,
                                      contributors=n))
    db.commit()


def figures(db, user, row):
    act_as(db, user.id)
    return service.class_figures(db, user.id, row.id)


# --- the rules, in one place -------------------------------------------------------

@pytest.mark.parametrize(("code", "ends"), [
    ("2025W1", date(2025, 12, 31)), ("2025W2", date(2026, 4, 30)),
    ("2026S1", date(2026, 6, 30)), ("2026S2", date(2026, 8, 31)),
    ("2025X1", None), ("25W1", None), ("", None), (None, None), ("abcdW1", None),
])
def test_term_codes_end_where_the_terms_do(code, ends):
    assert aggregates.term_code_end(code) == ends


def test_a_term_counts_only_once_its_asking_window_has_closed():
    ends = date(2025, 12, 31)
    assert not aggregates.term_closed("2025W1", ends + timedelta(days=COUNTED_AFTER_DAYS))
    assert aggregates.term_closed("2025W1", ends + timedelta(days=COUNTED_AFTER_DAYS + 1))
    assert not aggregates.term_closed("garbage", date(2099, 1, 1))


def test_the_wait_is_the_asking_window_and_the_database_says_the_same():
    assert COUNTED_AFTER_DAYS == ASK_UNTIL_DAYS
    read = rls.FUNCTION_SQL[rls.FUNCTION_SQL.index("FUNCTION account_grade_distribution"):]
    read = read[:read.index("$$;")]
    assert re.search(r"\+ (\d+) <", read).group(1) == str(COUNTED_AFTER_DAYS)
    assert re.search(r"HAVING sum\(d.contributors\) >= (\d+)", read).group(1) == str(COHORT_FLOOR)


@pytest.mark.parametrize(("code", "label"), [
    ("2025W1", "Fall 2025"), ("2025W2", "Winter 2026"), ("2026S1", "Spring 2026"), ("2026S2", "Summer 2026"),
    ("odd", "odd"),
])
def test_terms_read_the_way_students_say_them(code, label):
    assert service.term_label(code) == label


def test_the_median_band_is_where_the_middle_grade_falls():
    bands = [aggregates.Band("T", 70, 2), aggregates.Band("T", 80, 2), aggregates.Band("T", 90, 3)]
    assert service.median_bucket(bands) == 80
    assert service.median_bucket([aggregates.Band("T", 60, 5)]) == 60
    # An even count splits between two bands: the lower one holds the middle.
    assert service.median_bucket([aggregates.Band("T", 70, 2), aggregates.Band("T", 80, 2)]) == 70


# --- what a student sees ------------------------------------------------------------

def test_a_closed_term_at_the_floor_is_shown_with_its_median_and_your_band(db):
    sam = student(db)
    row = course(db, sam, average=74.0)
    counts(db, "CPSC 221", CLOSED, {70: 1, 80: 3, 90: 1})
    found = figures(db, sam, row)
    assert found.course_key == "CPSC 221" and found.floor == COHORT_FLOOR
    assert [(t.term_code, t.contributors, t.median_bucket) for t in found.distributions] == [(CLOSED, 5, 80)]
    assert [(b.bucket, b.contributors) for b in found.distributions[0].bands] == [(70, 1), (80, 3), (90, 1)]
    assert (found.your_grade, found.your_bucket) == (74.0, 70)


def test_terms_come_newest_first(db):
    sam = student(db)
    row = course(db, sam)
    counts(db, "CPSC 221", OLDER, {60: 5})
    counts(db, "CPSC 221", CLOSED, {80: 6})
    assert [t.term_code for t in figures(db, sam, row).distributions] == [CLOSED, OLDER]


def test_below_the_floor_a_term_is_not_shown_even_if_the_table_held_it(db):
    sam = student(db)
    row = course(db, sam)
    counts(db, "CPSC 221", CLOSED, {80: COHORT_FLOOR - 1})
    assert figures(db, sam, row).distributions == []


def test_a_term_still_being_answered_is_not_shown(db):
    sam = student(db)
    row = course(db, sam)
    counts(db, "CPSC 221", OPEN, {80: 9})
    assert figures(db, sam, row).distributions == []


def test_only_the_course_you_hold_is_read(db):
    sam = student(db)
    row = course(db, sam, code="CPSC 221")
    counts(db, "CPSC 310", CLOSED, {80: 9})
    counts(db, "UBCV CPSC 221", CLOSED, {80: 9})  # a different key: linked courses carry the campus
    assert figures(db, sam, row).distributions == []


def test_nothing_is_read_for_transfer_credit_or_a_code_that_isnt_a_course(db):
    sam = student(db)
    counts(db, "CPSC 221", CLOSED, {80: 9})
    transfer = course(db, sam, transfer_credit=True)
    odd = course(db, sam, code="Reading week")
    for row in (transfer, odd):
        found = figures(db, sam, row)
        assert found.course_key is None and found.distributions == []


def test_an_unmarked_course_has_no_band_of_its_own(db):
    sam = student(db)
    row = course(db, sam)
    found = figures(db, sam, row)
    assert (found.your_grade, found.your_bucket) == (None, None)


def test_someone_elses_course_answers_nothing(db):
    sam, alex = student(db, "Sam"), student(db, "Alex")
    row = course(db, alex)
    act_as(db, sam.id)
    assert service.class_figures(db, sam.id, row.id) is None


# --- the route ----------------------------------------------------------------------

def test_the_route_reads_your_own_course_and_refuses_anyone_elses(db):
    sam, alex = student(db, "Sam"), student(db, "Alex")
    mine, theirs = course(db, sam, average=88.0), course(db, alex)
    counts(db, "CPSC 221", CLOSED, {85: 5})
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app.main.app)
        headers = {"Authorization": f"Bearer {create_access_token(sam.id, sam.session_epoch or 0)}"}
        own = client.get(f"/api/grades/{sam.id}/courses/{mine.id}/class-figures", headers=headers)
        other = client.get(f"/api/grades/{sam.id}/courses/{theirs.id}/class-figures", headers=headers)
        foreign = client.get(f"/api/grades/{alex.id}/courses/{theirs.id}/class-figures", headers=headers)
    finally:
        app.main.app.dependency_overrides.clear()
    assert own.status_code == 200
    assert own.json()["distributions"][0]["bands"] == [{"bucket": 85, "contributors": 5}]
    assert own.json()["your_bucket"] == 85
    assert (other.status_code, foreign.status_code) == (404, 403)
