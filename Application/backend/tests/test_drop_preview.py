"""The course-drop simulator (Phase 4 item 11, §13.6).

Pinned: before and after through the dashboard's own functions (so a drop
preview can never disagree with the grades page); the full-time check against
the threshold (9 by default, D9) with loans, housing and study permits named;
the tuition share as a ceiling, or a plain "not recorded"; only this term's
courses; another user's course is a 404; nothing is written.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

import app.main
import app.Grades.services.drop_service as drop_service
from app._database.db import get_db
from app._database.models import CourseModel
from app.Auth.dependencies import get_current_user
from app.Finances.schemas.tuition import CourseCost
from app.Grades.schemas.grade import GradeCreate
from app.Grades.services.dash_services import get_dashboard
from app.Grades.services.drop_service import drop_preview
from app.Grades.services.grade_service import add_grade
from conftest import make_course, make_user


def mark(db, user, course, got):
    add_grade(db, user.id, course.id, GradeCreate(name=f"A {uuid.uuid4().hex[:4]}", category="Assignment",
                                                  score=got, max_score=100.0))


@pytest.fixture
def term(db, user):
    """Year 3 Fall: one finished course; this term 4 + 3 + 3 = 10 credits."""
    user.current_school_year = 3
    user.current_semester = "Fall"
    db.commit()
    make_course(db, user.id, "CPSC 110", year=2, semester="Fall", final_grade=88.0, credits=4.0)
    c310 = make_course(db, user.id, "CPSC 310", year=3, semester="Fall", credits=4.0)
    c320 = make_course(db, user.id, "CPSC 320", year=3, semester="Fall", credits=3.0)
    make_course(db, user.id, "PHIL 220", year=3, semester="Fall", credits=3.0)
    mark(db, user, c310, 72.0)
    mark(db, user, c320, 81.0)
    return {"310": c310, "320": c320}


def test_before_is_the_grades_page(db, user, term):
    preview = drop_preview(db, user.id, term["320"].id)
    page = get_dashboard(db, user.id)

    assert preview.before.semester_average == page.semester_average
    assert preview.before.cumulative_average == page.cumulative_average
    assert preview.before.cumulative_average_including_term == page.cumulative_average_including_term


def test_after_leaves_the_course_out(db, user, term):
    preview = drop_preview(db, user.id, term["320"].id)

    assert (preview.before.semester_average, preview.after.semester_average) == (76.5, 72.0)
    assert preview.after.cumulative_average_including_term == round((88 * 4 + 72 * 4) / 8, 2)
    assert preview.before.cumulative_average == preview.after.cumulative_average == 88.0
    assert (preview.before.term_credits, preview.after.term_credits) == (10.0, 7.0)


def test_archived_and_transfer_courses_carry_no_term_credits(db, user, term):
    make_course(db, user.id, "OLD 100", year=3, semester="Fall", credits=3.0, archived=True)
    make_course(db, user.id, "XFER 100", year=3, semester="Fall", credits=3.0, transfer_credit=True)

    assert drop_preview(db, user.id, term["320"].id).before.term_credits == 10.0


def test_falling_under_full_time_is_warned_with_what_it_can_affect(db, user, term):
    preview = drop_preview(db, user.id, term["320"].id)

    assert preview.was_full_time and preview.below_full_time and preview.full_time_credits == 9.0
    first = preview.warnings[0]
    for named in ("student loans", "housing", "study permit", "7 credits", "9"):
        assert named in first
    assert any("12 credits" in w for w in preview.warnings)


def test_staying_full_time_has_no_full_time_warning(db, user, term):
    preview = drop_preview(db, user.id, term["320"].id, full_time_credits=6.0)

    assert not preview.below_full_time
    assert not any("full-time" in w for w in preview.warnings)


def test_the_threshold_is_yours_to_set(db, user, term):
    assert drop_preview(db, user.id, term["320"].id, full_time_credits=12.0).was_full_time is False


def test_no_tuition_recorded_says_so(db, user, term):
    preview = drop_preview(db, user.id, term["320"].id)

    assert preview.tuition_share is None
    assert any("No tuition is recorded" in w for w in preview.warnings)


def test_the_tuition_share_is_a_ceiling_with_its_caveat(db, user, term, monkeypatch):
    monkeypatch.setattr(drop_service, "course_cost", lambda _db, _u, cid: CourseCost(
        course_id=cid, credits=3.0, cost_per_credit=200.0, tuition_share=600.0, materials=[],
        materials_total=0.0, total=600.0))

    preview = drop_preview(db, user.id, term["320"].id)

    assert preview.tuition_share == 600.0
    assert any("$600.00" in w and "refund deadline" in w for w in preview.warnings)


def test_only_this_terms_courses(db, user, term):
    past = db.query(CourseModel).filter(CourseModel.code == "CPSC 110").one()

    with pytest.raises(ValueError):
        drop_preview(db, user.id, past.id)


def test_another_users_course_is_not_found(db, user, term):
    stranger = make_user(db, "stranger@example.com")

    assert drop_preview(db, stranger.id, term["320"].id) is None


def test_nothing_is_written(db, user, term):
    def snapshot():
        db.expire_all()
        return sorted((c.code, c.archived, c.average, c.final_grade) for c in
                      db.query(CourseModel).filter(CourseModel.user_id == user.id).all())

    before = snapshot()
    drop_preview(db, user.id, term["320"].id)

    assert snapshot() == before


@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_route(db, user, term, client):
    url = f"/api/grades/{user.id}/courses/{term['320'].id}/drop-preview"

    body = client.get(url).json()
    assert body["below_full_time"] is True and body["after"]["term_credits"] == 7.0
    assert client.get(url + "?full_time_credits=6").json()["below_full_time"] is False
    assert client.get(url + "?full_time_credits=0").status_code == 422
    past = db.query(CourseModel).filter(CourseModel.code == "CPSC 110").one()
    assert client.get(f"/api/grades/{user.id}/courses/{past.id}/drop-preview").status_code == 422
    assert client.get(f"/api/grades/{user.id}/courses/{uuid.uuid4()}/drop-preview").status_code == 404
