"""What term reviews say about a course (Phase 3 item 5, D11), on SQLite and Postgres.

The promises: one answer per person per course, only from counted terms, live
accounts and reviews not skipped; a figure below the floor is never written and
never read; the sealed table holds no user id; the recount and its SQLite twin
agree; and a student reads only the course their own course is counted under.
"""
import re
import uuid
from datetime import date

import pytest

from app._database import aggregates, recounts, rls
from app._database.identity import act_as
from app._database.models import COHORT_FLOOR, Base, CourseIntelModel, CourseModel, TermReviewModel, utc_now
from app.Grades.services import class_figures_service as service
from conftest import make_user

TODAY = date.today()
CLOSED = f"{TODAY.year - 2}W1"
EARLIER = f"{TODAY.year - 3}W1"
OPEN = f"{TODAY.year}W1"


def reviewer(db, key="CPSC 221", term=CLOSED, hours=8, difficulty=4, clarity=3, again=True, **extra):
    """One person, one course, one review."""
    person = make_user(db, f"r-{uuid.uuid4().hex[:8]}@example.com")
    return review(db, person, key, term, hours, difficulty, clarity, again, **extra)


def review(db, person, key, term, hours=8, difficulty=4, clarity=3, again=True, code=None, **extra):
    course = CourseModel(id=uuid.uuid4(), user_id=person.id, code=code or key, name="x", semester="Fall", year=2,
                         credits=4.0)
    db.add(course)
    db.flush()
    db.add(TermReviewModel(id=uuid.uuid4(), user_id=person.id, course_id=course.id, course_key=key,
                           term_code=term, hours_per_week=hours, difficulty=difficulty, clarity=clarity,
                           would_take_again=again, **extra))
    db.commit()
    return person


def recount(db):
    return aggregates.recount_course_intel(db)


def read(db, key="CPSC 221"):
    act_as(db, make_user(db, f"reader-{uuid.uuid4().hex[:6]}@example.com").id)
    return aggregates.course_intel(db, key)


def test_five_reviews_give_every_figure(db):
    for hours, difficulty, clarity, again in [(6, 3, 4, True), (8, 4, 4, True), (9, 4, 3, False),
                                              (10, 5, 5, True), (12, 2, 4, False)]:
        reviewer(db, hours=hours, difficulty=difficulty, clarity=clarity, again=again)
    assert recount(db) == 1
    intel = read(db)
    assert (intel.hours_answers, intel.hours_median) == (5, 9.0)
    assert (intel.difficulty_answers, intel.difficulty_mean) == (5, pytest.approx(3.6))
    assert (intel.clarity_answers, intel.clarity_mean) == (5, pytest.approx(4.0))
    assert (intel.again_answers, intel.again_share) == (5, pytest.approx(60.0))


def test_below_the_floor_nothing_is_written(db):
    for _ in range(COHORT_FLOOR - 1):
        reviewer(db)
    assert recount(db) == 0
    assert read(db) is None


def test_each_figure_has_its_own_floor(db):
    """Five people answered hours, but only two said whether they'd take it again:
    a share of two answers is never written, let alone shown."""
    for i in range(COHORT_FLOOR):
        reviewer(db, again=True if i < 2 else None, clarity=None)
    recount(db)
    intel = read(db)
    assert intel.hours_answers == COHORT_FLOOR
    assert (intel.again_answers, intel.again_share) == (None, None)
    assert (intel.clarity_answers, intel.clarity_mean) == (None, None)
    raw = db.query(CourseIntelModel).one()
    assert (raw.again_answers, raw.again_share) == (None, None), "below the floor it isn't even stored"


def test_terms_still_being_answered_and_skipped_reviews_are_left_out(db):
    for _ in range(COHORT_FLOOR - 1):
        reviewer(db)
    reviewer(db, term=OPEN)
    reviewer(db, skipped=True)
    assert recount(db) == 0


def test_a_deleted_account_is_left_out(db):
    people = [reviewer(db) for _ in range(COHORT_FLOOR)]
    people[0].deleted_at = utc_now()
    db.commit()
    assert recount(db) == 0


def test_one_answer_per_person_their_latest(db):
    """Someone who took the course twice counts once, with their latest term."""
    repeat = reviewer(db, term=EARLIER, hours=40)
    review(db, repeat, "CPSC 221", CLOSED, hours=10, code="CPSC 221 retake")
    for _ in range(COHORT_FLOOR - 2):
        reviewer(db, hours=10)
    assert recount(db) == 0, "four people, however many reviews"
    reviewer(db, hours=10)
    recount(db)
    assert (read(db).hours_answers, read(db).hours_median) == (COHORT_FLOOR, 10.0)


def test_courses_are_kept_apart_and_a_recount_replaces_the_table(db):
    for _ in range(COHORT_FLOOR):
        reviewer(db, key="CPSC 221", hours=5)
        reviewer(db, key="MATH 200", hours=15)
    assert recount(db) == 2
    assert (read(db, "CPSC 221").hours_median, read(db, "MATH 200").hours_median) == (5.0, 15.0)
    for row in db.query(TermReviewModel).filter(TermReviewModel.course_key == "MATH 200"):
        row.skipped = True
    db.commit()
    assert recount(db) == 1
    assert read(db, "MATH 200") is None


def test_the_table_holds_no_user_id_or_anything_per_person():
    for name in rls.SEALED_TABLES:
        columns = set(Base.metadata.tables[name].columns.keys())
        assert not any("user" in c or (c.endswith("_id") and c != "id") for c in columns), (name, columns)


def test_the_floor_in_the_functions_is_the_models():
    for name in ("account_recount_course_intel", "account_course_intel"):
        body = rls.FUNCTION_SQL[rls.FUNCTION_SQL.index(f"FUNCTION {name}("):]
        body = body[:body.index("$$;")]
        floors = set(re.findall(r">= (\d+)", body))
        assert floors == {str(COHORT_FLOOR)}, (name, floors)


def test_the_daily_recount_runs_it(db):
    for _ in range(COHORT_FLOOR):
        reviewer(db)
    assert recounts.run_all(db)["course_intel"] == 1


# --- on the course page ---------------------------------------------------------------

def test_the_course_page_shows_the_figures_rounded(db):
    for hours in (6, 7, 8, 9, 11):
        reviewer(db, hours=hours, difficulty=4, clarity=4, again=hours < 9)
    recount(db)
    sam = make_user(db, "sam@example.com")
    course = CourseModel(id=uuid.uuid4(), user_id=sam.id, code="CPSC 221", name="x", semester="Fall", year=3,
                         credits=4.0)
    db.add(course)
    db.commit()
    act_as(db, sam.id)
    intel = service.class_figures(db, sam.id, course.id).intel
    assert (intel.hours_median, intel.difficulty_mean, intel.clarity_mean, intel.again_share) == (8.0, 4.0, 4.0, 60)


def test_no_figure_at_the_floor_reads_as_none(db):
    sam = make_user(db, "sam@example.com")
    course = CourseModel(id=uuid.uuid4(), user_id=sam.id, code="CPSC 221", name="x", semester="Fall", year=3,
                         credits=4.0)
    db.add(course)
    db.commit()
    act_as(db, sam.id)
    assert service.class_figures(db, sam.id, course.id).intel is None
    assert service.intel_out(aggregates.CourseIntel(None, None, None, None, None, None, None, None)) is None


def test_figures_are_rounded_for_showing_not_truncated():
    shown = service.intel_out(aggregates.CourseIntel(6, 8.25, 6, 3.6667, 6, 4.04, 6, 66.667))
    assert (shown.hours_median, shown.difficulty_mean, shown.clarity_mean, shown.again_share) == (8.2, 3.7, 4.0, 67)
