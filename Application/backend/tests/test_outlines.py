"""Shared course outlines (Phase 3 item 2, D12), on SQLite and Postgres.

The promises: an outline holds weights and assessments' names, categories and due
dates, never a score or a note; an offer reaches nobody until the owner's review
approves it; only an empty course is filled, and it stays the student's own; the
review shows how many accounts offered a group, never who; and only the course
in the path, the caller's own, is touched.
"""
import sys
import uuid
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import app.main  # noqa: E402
import outline_review as review  # noqa: E402
from app._database.db import get_db  # noqa: E402
from app._database.identity import act_as  # noqa: E402
from app._database.models import (  # noqa: E402
    CourseCategoryWeightModel, CourseModel, GradeModel, OutlineOfferModel, SharedOutlineModel, TaskModel,
)
from app.Auth.services.session_service import create_access_token  # noqa: E402
from app.Grades.services import outline_service as service  # noqa: E402
from conftest import make_user  # noqa: E402

#: Fall of school year 3 for a student whose first year began in 2024: "2026W1".
TERM = "2026W1"


def student(db, name="sam", first_year=2024):
    user = make_user(db, f"{name}-{uuid.uuid4().hex[:6]}@example.com")
    user.first_year_calendar_year = first_year
    db.commit()
    act_as(db, user.id)
    return user


def course(db, user, code="CPSC 221", weights=None, **extra):
    row = CourseModel(id=uuid.uuid4(), user_id=user.id, code=code, name="Algorithms", semester="Fall", year=3,
                      credits=4.0, **extra)
    db.add(row)
    db.flush()
    for category, weight in (weights or {}).items():
        db.add(CourseCategoryWeightModel(course_id=row.id, category=category, weight=weight))
    db.commit()
    return row


def filled(db, user):
    """A course with weights, a marked midterm with a note-like name, and a dated assignment."""
    row = course(db, user, weights={"Assignment": 40.0, "Midterm": 20.0, "Final": 40.0, "Quiz": 0.0})
    db.add(GradeModel(id=uuid.uuid4(), course_id=row.id, name="Midterm 1", category="Midterm", score=71.0,
                      max_score=100.0, due_date=date(2026, 10, 15)))
    db.add(GradeModel(id=uuid.uuid4(), course_id=row.id, name="Assignment 1", category="Assignment", score=None,
                      max_score=20.0, due_date=date(2026, 9, 20)))
    db.add(GradeModel(id=uuid.uuid4(), course_id=row.id, name="Participation", category="Assignment", score=10.0,
                      max_score=10.0))
    db.commit()
    db.refresh(row)
    return row


def approve_all(db):
    for group in review.pending_groups(db):
        review.approve(db, group.id)


# --- offering ----------------------------------------------------------------------------

def test_an_outline_holds_the_shape_and_never_a_score(db):
    sam = student(db)
    row = filled(db, sam)
    service.offer(db, sam.id, row.id)
    offer = db.query(OutlineOfferModel).one()
    assert (offer.course_key, offer.term_code, offer.status) == ("CPSC 221", TERM, "pending")
    assert offer.outline == {
        "weights": {"Assignment": 40.0, "Midterm": 20.0, "Final": 40.0},
        "assessments": [
            {"name": "Assignment 1", "category": "Assignment", "due_date": "2026-09-20"},
            {"name": "Midterm 1", "category": "Midterm", "due_date": "2026-10-15"},
            {"name": "Participation", "category": "Assignment", "due_date": None},
        ],
    }
    assert "71" not in str(offer.outline) and "score" not in str(offer.outline)


def test_offering_again_replaces_and_resets_review(db):
    sam = student(db)
    row = filled(db, sam)
    service.offer(db, sam.id, row.id)
    db.query(OutlineOfferModel).update({"status": "rejected"})
    db.commit()
    db.add(GradeModel(id=uuid.uuid4(), course_id=row.id, name="Final", category="Final", max_score=100.0))
    db.commit()
    db.refresh(row)
    found = service.offer(db, sam.id, row.id)
    assert found.offer.status == "pending"
    assert db.query(OutlineOfferModel).count() == 1
    assert len(db.query(OutlineOfferModel).one().outline["assessments"]) == 4


@pytest.mark.parametrize(("setup", "says"), [
    (lambda db, u: course(db, u, weights={"Final": 100.0}, transfer_credit=True), "Transfer credit"),
    (lambda db, u: course(db, u, code="Study group", weights={"Final": 100.0}), "isn't a course code"),
    (lambda db, u: course(db, u, weights={}), "weights first"),
])
def test_an_outline_that_couldnt_be_found_or_used_cant_be_offered(db, setup, says):
    sam = student(db)
    row = setup(db, sam)
    assert service.status(db, sam.id, row.id).can_offer is False
    with pytest.raises(service.OutlineError, match=says):
        service.offer(db, sam.id, row.id)


def test_without_the_first_year_setting_the_term_is_unknown(db):
    sam = student(db, first_year=None)
    row = filled(db, sam)
    with pytest.raises(service.OutlineError, match="first year"):
        service.offer(db, sam.id, row.id)


def test_withdrawing_takes_the_offer_back(db):
    sam = student(db)
    row = filled(db, sam)
    service.offer(db, sam.id, row.id)
    assert service.withdraw(db, sam.id, row.id) is True
    assert service.withdraw(db, sam.id, row.id) is False
    assert db.query(OutlineOfferModel).count() == 0


def test_an_offer_reaches_nobody_before_review(db):
    sam, alex = student(db, "sam"), student(db, "alex")
    service.offer(db, sam.id, filled(db, sam).id)
    empty = course(db, alex)
    found = service.status(db, alex.id, empty.id)
    assert (found.shared, found.can_apply) == (None, False)


def test_nobody_offers_reads_or_fills_someone_elses_course(db):
    sam, alex = student(db, "sam"), student(db, "alex")
    theirs = filled(db, alex)
    act_as(db, sam.id)
    assert service.status(db, sam.id, theirs.id) is None
    assert service.offer(db, sam.id, theirs.id) is None
    assert service.withdraw(db, sam.id, theirs.id) is False
    assert service.apply(db, sam.id, theirs.id) is None


def test_deleting_the_course_takes_its_offer(db):
    sam = student(db)
    row = filled(db, sam)
    service.offer(db, sam.id, row.id)
    db.delete(row)
    db.commit()
    assert db.query(OutlineOfferModel).count() == 0


# --- review --------------------------------------------------------------------------------

def test_the_review_groups_offers_and_counts_accounts_never_names(db):
    sam, alex = student(db, "sam"), student(db, "alex")
    service.offer(db, sam.id, filled(db, sam).id)
    service.offer(db, alex.id, filled(db, alex).id)
    [group] = review.pending_groups(db)
    assert len(group.accounts) == 2
    lines = "\n".join(review.listing(db))
    assert "CPSC 221  2026W1" in lines and "(2 accounts)" in lines
    assert "Midterm 1 (Midterm, 2026-10-15)" in lines
    assert sam.email not in lines and str(sam.id) not in lines


def test_approving_shares_it_and_marks_the_offers(db):
    sam = student(db)
    service.offer(db, sam.id, filled(db, sam).id)
    message = review.approve(db, review.pending_groups(db)[0].id)
    assert "CPSC 221 2026W1" in message
    shared = db.query(SharedOutlineModel).one()
    assert (shared.course_key, shared.term_code, shared.source) == ("CPSC 221", TERM, "reviewed-offer")
    assert db.query(OutlineOfferModel).one().status == "accepted"
    assert review.listing(db) == ["Nothing pending."]


def test_an_existing_outline_is_replaced_only_when_asked(db):
    sam, alex = student(db, "sam"), student(db, "alex")
    service.offer(db, sam.id, filled(db, sam).id)
    approve_all(db)
    other = course(db, alex, weights={"Final": 100.0})
    service.offer(db, alex.id, other.id)
    gid = review.pending_groups(db)[0].id
    assert "already shared" in "\n".join(review.listing(db))
    with pytest.raises(SystemExit, match="--replace"):
        review.approve(db, gid)
    review.approve(db, gid, replace=True)
    assert db.query(SharedOutlineModel).one().outline["weights"] == {"Final": 100.0}


def test_rejecting_shares_nothing(db):
    sam = student(db)
    service.offer(db, sam.id, filled(db, sam).id)
    review.reject(db, review.pending_groups(db)[0].id)
    assert db.query(SharedOutlineModel).count() == 0
    assert db.query(OutlineOfferModel).one().status == "rejected"


def test_the_review_needs_its_variable(monkeypatch, capsys):
    monkeypatch.delenv(review.VARIABLE, raising=False)
    assert review.main([]) == 2
    assert review.VARIABLE in capsys.readouterr().err


# --- filling a course --------------------------------------------------------------------------

def test_a_classmate_fills_an_empty_course_from_the_reviewed_outline(db):
    sam, alex = student(db, "sam"), student(db, "alex")
    service.offer(db, sam.id, filled(db, sam).id)
    approve_all(db)
    act_as(db, alex.id)
    empty = course(db, alex, weights={"Assignment": 50.0, "Final": 50.0, "Quiz": 10.0})
    before = service.status(db, alex.id, empty.id)
    assert before.can_apply is True and len(before.shared.outline.assessments) == 3
    after = service.apply(db, alex.id, empty.id)
    assert after.can_apply is False
    db.expire_all()
    mine = db.get(CourseModel, empty.id)
    assert {c: w for c, w in mine.category_weights.items() if w} == {"Assignment": 40.0, "Midterm": 20.0,
                                                                     "Final": 40.0}
    grades = {g.name: g for g in mine.grades}
    assert set(grades) == {"Assignment 1", "Midterm 1", "Participation"}
    assert all(g.score is None for g in grades.values()), "nobody's marks travel"
    assert grades["Midterm 1"].schedule_as == "event" and grades["Assignment 1"].schedule_as == "task"
    assert db.query(TaskModel).filter(TaskModel.user_id == alex.id, TaskModel.grade_id ==
                                      grades["Assignment 1"].id).count() == 1


def test_a_course_with_grades_is_never_written_over(db):
    sam, alex = student(db, "sam"), student(db, "alex")
    service.offer(db, sam.id, filled(db, sam).id)
    approve_all(db)
    act_as(db, alex.id)
    started = filled(db, alex)
    assert service.status(db, alex.id, started.id).can_apply is False
    with pytest.raises(service.OutlineError, match="already has grades"):
        service.apply(db, alex.id, started.id)


def test_another_term_or_course_gets_nothing(db):
    sam, alex = student(db, "sam"), student(db, "alex", first_year=2023)
    service.offer(db, sam.id, filled(db, sam).id)
    approve_all(db)
    act_as(db, alex.id)
    later = course(db, alex)  # school year 3 from 2023 is 2025W1
    elsewhere = course(db, alex, code="CPSC 310")
    for row in (later, elsewhere):
        assert service.status(db, alex.id, row.id).shared is None
        with pytest.raises(service.OutlineError, match="no reviewed outline"):
            service.apply(db, alex.id, row.id)


# --- the routes ----------------------------------------------------------------------------------

def test_the_routes_offer_read_withdraw_and_refuse_someone_elses(db):
    sam, alex = student(db, "sam"), student(db, "alex")
    mine, theirs = filled(db, sam), filled(db, alex)
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app.main.app)
        headers = {"Authorization": f"Bearer {create_access_token(sam.id, sam.session_epoch or 0)}"}
        base = f"/api/grades/{sam.id}/courses"
        offered = client.post(f"{base}/{mine.id}/outline/offer", headers=headers)
        read = client.get(f"{base}/{mine.id}/outline", headers=headers)
        other = client.get(f"{base}/{theirs.id}/outline", headers=headers)
        no_outline = client.post(f"{base}/{mine.id}/outline/apply", headers=headers)
        withdrawn = client.delete(f"{base}/{mine.id}/outline/offer", headers=headers)
    finally:
        app.main.app.dependency_overrides.clear()
    assert offered.status_code == 200 and offered.json()["offer"]["status"] == "pending"
    assert read.json()["course_key"] == "CPSC 221" and read.json()["term_code"] == TERM
    assert (other.status_code, no_outline.status_code, withdrawn.status_code) == (404, 400, 200)
