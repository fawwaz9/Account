"""End-of-term reviews and the anonymous grade count (Phase 2 item 13, D25).

Runs on SQLite and on Postgres: the recount has a definer-function path and a
plain-query path that must mean the same.

The promises under test: your review holds no copy of your grade; a grade is
counted only if you opted in, and only into a course-term with at least
COHORT_FLOOR contributors; withdrawing takes effect at the next recount; and
no route ever answers with a count.
"""
import re
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database import distributions, recounts, rls
from app._database.db import get_db
from app._database.identity import act_as
from app._database.models import COHORT_FLOOR, CourseModel, GradeDistributionModel, TermReviewModel, utc_now
from app.Auth.services.session_service import create_access_token
from app.config import settings
from app.Grades.schemas.term_review import TermReviewIn
from app.Grades.services import term_review_service as reviews
from app.Users.services.user_service import delete_user
from conftest import make_user

#: Summer of school year 2 for a student whose first year began in 2024: it
#: ran July to August 2026, so by mid-October it is in its asking window.
TODAY = date(2026, 10, 11)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(reviews, "user_today", lambda db, user_id, at=None: TODAY)


def student(db, name="Sam"):
    user = make_user(db, f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com")
    user.name, user.first_year_calendar_year = name, 2024
    db.commit()
    return user


def course(db, user, code="CPSC 221", semester="Summer", year=2, final=82.0, average=0.0, **extra):
    row = CourseModel(id=uuid.uuid4(), user_id=user.id, code=code, name="Algorithms", semester=semester,
                      year=year, credits=4.0, final_grade=final, average=average, **extra)
    db.add(row)
    db.commit()
    return row


def answer(db, user, row, **fields):
    act_as(db, user.id)
    data = {"hours_per_week": 8, "difficulty": 4, "clarity": 3, "would_take_again": True,
            "contribute_grade": False, **fields}
    return reviews.save(db, user.id, row.id, TermReviewIn(**data))


def counts(db):
    db.expire_all()
    return sorted((r.course_key, r.term_code, r.bucket, r.contributors) for r in db.query(GradeDistributionModel))


def contributors(db, n, grade, code="CPSC 221"):
    people = []
    for i in range(n):
        user = student(db, f"P{i}")
        row = course(db, user, code=code, final=grade)
        answer(db, user, row, contribute_grade=True)
        people.append((user, row))
    return people


# --- when it asks -----------------------------------------------------------------

def test_it_asks_about_a_term_that_ended_two_weeks_ago_and_not_an_old_one(db):
    sam = student(db)
    recent = course(db, sam, code="CPSC 221", semester="Summer", year=2)
    course(db, sam, code="CPSC 210", semester="Fall", year=2)          # ended December 2025
    course(db, sam, code="CPSC 310", semester="Fall", year=3)          # still running
    course(db, sam, code="MATH 100", semester="Summer", year=2, transfer_credit=True)
    act_as(db, sam.id)
    found = reviews.overview(db, sam.id)
    assert [(c.course_id, c.term_label) for c in found.courses] == [(recent.id, "Summer 2026")]
    assert found.pending == 1


def test_it_does_not_ask_in_the_fortnight_grades_take_to_post(db, monkeypatch):
    sam = student(db)
    course(db, sam)
    monkeypatch.setattr(reviews, "user_today", lambda db, user_id, at=None: date(2026, 9, 10))
    act_as(db, sam.id)
    assert reviews.overview(db, sam.id).courses == []


def test_without_the_first_year_setting_nothing_is_asked(db):
    sam = student(db)
    sam.first_year_calendar_year = None
    db.commit()
    course(db, sam)
    act_as(db, sam.id)
    assert reviews.overview(db, sam.id).courses == []


@pytest.mark.parametrize(("semester", "year", "code"), [
    ("Fall", 2, "2025W1"), ("Winter", 2, "2025W2"), ("Spring", 2, "2026S1"), ("Summer", 2, "2026S2"),
])
def test_terms_are_named_the_way_ubc_names_them(db, semester, year, code):
    sam = student(db)
    assert reviews.term_code_of(course(db, sam, semester=semester, year=year), 2024) == code


def test_the_course_key_keeps_the_campus_when_the_code_says_it(db):
    sam = student(db)
    assert reviews.course_key_of(db, course(db, sam, code="CPSC_V 221")) == "UBCV CPSC 221"
    assert reviews.course_key_of(db, course(db, sam, code="MATH 100")) == "MATH 100"


# --- answering --------------------------------------------------------------------

def test_your_review_holds_no_copy_of_your_grade(db):
    columns = {c.name for c in TermReviewModel.__table__.columns}
    assert not {c for c in columns if "grade" in c} - {"contribute_grade"}
    assert not {"final_grade", "average", "score", "bucket"} & columns
    sam = student(db)
    # 87.3: a timestamp can't contain it (seconds stop at 59), so finding it
    # means the grade itself came back.
    saved = answer(db, sam, course(db, sam, final=87.3), contribute_grade=True)
    assert "87.3" not in saved.model_dump_json()


def test_contributing_needs_a_grade(db):
    sam = student(db)
    ungraded = course(db, sam, final=0.0, average=0.0)
    with pytest.raises(reviews.ReviewError, match="no grade"):
        answer(db, sam, ungraded, contribute_grade=True)
    assert answer(db, sam, ungraded).contribute_grade is False


def test_a_course_out_of_its_window_cannot_be_reviewed(db):
    sam = student(db)
    with pytest.raises(reviews.ReviewError, match="isn't one to review"):
        answer(db, sam, course(db, sam, semester="Fall", year=2))


def test_answers_lock_after_a_fortnight_but_the_contribution_never_does(db):
    sam = student(db)
    row = course(db, sam)
    answer(db, sam, row)
    review = db.query(TermReviewModel).filter_by(course_id=row.id).one()
    review.created_at = utc_now() - timedelta(days=reviews.EDIT_DAYS + 1)
    db.commit()
    with pytest.raises(reviews.ReviewError, match="locked"):
        answer(db, sam, row, difficulty=1)
    assert answer(db, sam, row, contribute_grade=True).contribute_grade is True
    assert answer(db, sam, row, contribute_grade=False).answers_editable is False


def test_skipping_asks_no_more_and_answering_later_still_works(db):
    sam = student(db)
    row = course(db, sam)
    act_as(db, sam.id)
    assert reviews.skip(db, sam.id, row.id).skipped is True
    assert reviews.overview(db, sam.id).pending == 0
    assert answer(db, sam, row).skipped is False
    act_as(db, sam.id)
    with pytest.raises(reviews.ReviewError, match="already answered"):
        reviews.skip(db, sam.id, row.id)


def test_nobody_reviews_or_deletes_someone_elses_course(db):
    sam, eve = student(db, "Sam"), student(db, "Eve")
    row = course(db, sam)
    answer(db, sam, row, contribute_grade=True)
    act_as(db, eve.id)
    assert reviews.save(db, eve.id, row.id, TermReviewIn(difficulty=1, contribute_grade=False)) is None
    assert reviews.skip(db, eve.id, row.id) is None
    assert reviews.remove(db, eve.id, row.id) is False
    assert db.query(TermReviewModel).filter_by(course_id=row.id).one().contribute_grade is True


# --- the count ----------------------------------------------------------------------

def test_the_floor_in_the_database_function_is_the_models(db):
    found = re.search(r"HAVING count\(\*\) >= (\d+)", rls.FUNCTION_SQL)
    assert found and int(found.group(1)) == COHORT_FLOOR


def test_below_the_floor_nothing_is_written_at_all(db):
    contributors(db, COHORT_FLOOR - 1, 82.0)
    assert distributions.recount(db) == 0
    assert counts(db) == []


def test_at_the_floor_bands_are_counted_and_nothing_else_is_kept(db):
    contributors(db, 3, 82.0)
    contributors(db, 2, 91.0)
    assert distributions.recount(db) == 2
    assert counts(db) == [("CPSC 221", "2026S2", 80, 3), ("CPSC 221", "2026S2", 90, 2)]


@pytest.mark.parametrize(("grade", "band"), [(49.9, 0), (50.0, 50), (54.9, 50), (99.0, 95), (103.0, 95)])
def test_the_bands(db, grade, band):
    assert distributions.bucket_of(grade) == band


def test_only_those_who_opted_in_are_counted_and_withdrawing_takes_effect_at_the_next_recount(db):
    people = contributors(db, COHORT_FLOOR, 82.0)
    bystander = student(db, "Bystander")
    answer(db, bystander, course(db, bystander, final=82.0))  # answered, did not opt in
    distributions.recount(db)
    assert counts(db) == [("CPSC 221", "2026S2", 80, COHORT_FLOOR)]
    user, row = people[0]
    answer(db, user, row, contribute_grade=False)
    distributions.recount(db)
    assert counts(db) == [], "one withdrawal takes the group below the floor"


def test_the_grade_is_read_at_recount_time_final_first_then_the_average(db):
    people = contributors(db, COHORT_FLOOR, 82.0)
    for _user, row in people:
        row.average = 61.0  # a running average the final grade should win over
    _user, no_final = people[0]
    no_final.final_grade = 0.0
    no_final.average = 91.0  # no final: the average stands in
    db.commit()
    distributions.recount(db)
    assert counts(db) == [("CPSC 221", "2026S2", 80, COHORT_FLOOR - 1), ("CPSC 221", "2026S2", 90, 1)]


def test_grades_of_100_and_over_are_counted_in_the_top_band(db):
    contributors(db, 2, 100.0)
    contributors(db, COHORT_FLOOR - 2, 104.0)
    distributions.recount(db)
    assert counts(db) == [("CPSC 221", "2026S2", 95, COHORT_FLOOR)]


def test_a_deleted_account_skipped_reviews_and_transfer_credit_are_left_out(db):
    people = contributors(db, COHORT_FLOOR + 2, 82.0)
    gone, _ = people[0]
    act_as(db, gone.id)
    delete_user(db, gone.id)
    _, transferred = people[1]
    transferred.transfer_credit = True
    db.commit()
    distributions.recount(db)
    assert counts(db) == [("CPSC 221", "2026S2", 80, COHORT_FLOOR)]


def test_a_skipped_review_is_never_counted_even_if_a_row_says_contribute(db):
    """The service can't produce this row; the recount still refuses it."""
    contributors(db, COHORT_FLOOR - 1, 82.0)
    odd = student(db, "Odd")
    row = course(db, odd, final=82.0)
    db.add(TermReviewModel(id=uuid.uuid4(), user_id=odd.id, course_id=row.id, course_key="CPSC 221",
                           term_code="2026S2", contribute_grade=True, skipped=True))
    db.commit()
    distributions.recount(db)
    assert counts(db) == []


def test_a_recount_replaces_the_table_whole(db):
    db.add(GradeDistributionModel(course_key="STALE 100", term_code="2020W1", bucket=50, contributors=9))
    db.commit()
    distributions.recount(db)
    assert counts(db) == []


# --- through the API ------------------------------------------------------------------

def signed_in(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.session_epoch or 0)}"}


def test_the_api_never_answers_with_a_count(db):
    contributors(db, COHORT_FLOOR, 87.3)
    distributions.recount(db)
    sam = student(db)
    row = course(db, sam, final=87.3)
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app.main.app)
        listed = client.get(f"/api/grades/{sam.id}/term-reviews", headers=signed_in(sam))
        saved = client.put(f"/api/grades/{sam.id}/term-reviews/{row.id}", headers=signed_in(sam),
                           json={"difficulty": 4, "contribute_grade": True})
        out_of_range = client.put(f"/api/grades/{sam.id}/term-reviews/{row.id}", headers=signed_in(sam),
                                  json={"difficulty": 9})
    finally:
        app.main.app.dependency_overrides.clear()
    assert listed.status_code == 200 and saved.status_code == 200 and out_of_range.status_code == 422
    for response in (listed, saved):
        assert "contributors" not in response.text and "bucket" not in response.text
        assert "87.3" not in response.text


def test_the_recount_door_is_for_the_scheduler_alone(db, monkeypatch):
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app.main.app)
        monkeypatch.setattr(settings, "CRON_SECRET", None)
        unconfigured = client.post("/api/internal/distributions/recount")
        monkeypatch.setattr(settings, "CRON_SECRET", "the-real-secret")
        wrong = client.post("/api/internal/distributions/recount", headers={"X-Cron-Secret": "a-guess"})
        right = client.post("/api/internal/distributions/recount", headers={"X-Cron-Secret": "the-real-secret"})
    finally:
        app.main.app.dependency_overrides.clear()
    assert (unconfigured.status_code, wrong.status_code, right.status_code) == (404, 403, 200)
    assert set(right.json()) == {key for key, _ in recounts.RECOUNTS}
    assert all(isinstance(n, int) for n in right.json().values()), "how many, never what"
