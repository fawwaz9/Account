"""The course section: optional, and called out in Attention for current courses.

A syllabus and a class schedule belong to one section, not to a course code, so
the section is what a syllabus will be matched on. It is never required -- a
course is still a course without one -- but a current course missing it says
so. Past courses do not: syllabi change every term.
"""
import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app.Auth.dependencies import get_current_user
from app.Grades.schemas.course import CourseCreate, CourseUpdate
from app.Grades.services.course_service import create_course, update_course
from app.Grades.services.dash_services import collect_attention
from app.Grades.utils.terms import CURRENT, FUTURE, PAST
from conftest import make_course


def bucketed(course, bucket):
    course.term_bucket = bucket
    return course


def section_items(courses):
    return [item for item in collect_attention(courses, 0.0) if item.kind == "missing_section"]


# --- Attention -------------------------------------------------------------

def test_a_current_course_without_a_section_is_called_out(db, user):
    course = bucketed(make_course(db, user.id, "CPSC 221"), CURRENT)
    [item] = section_items([course])
    assert (item.course_id, item.course_code) == (course.id, "CPSC 221")
    assert "section" in item.message


def test_a_current_course_with_a_section_is_not(db, user):
    course = bucketed(make_course(db, user.id, "CPSC 221", section="101"), CURRENT)
    assert section_items([course]) == []


@pytest.mark.parametrize("bucket", [PAST, FUTURE])
def test_only_current_courses_are_asked(db, user, bucket):
    """Syllabi change every term: a past course's section helps nothing."""
    course = bucketed(make_course(db, user.id, "CPSC 221", final_grade=80.0), bucket)
    assert section_items([course]) == []


@pytest.mark.parametrize("flag", ["transfer_credit", "archived"])
def test_a_transfer_credit_or_archived_course_is_not_asked(db, user, flag):
    course = bucketed(make_course(db, user.id, "MATH 100", **{flag: True}), CURRENT)
    assert section_items([course]) == []


def test_it_comes_after_everything_that_moves_a_grade(db, user):
    course = bucketed(make_course(db, user.id, "CPSC 221", category_weights={"Final": 50.0}), CURRENT)
    kinds = [item.kind for item in collect_attention([course], 0.0)]
    assert kinds == ["weight_problem", "missing_section"]


# --- storing it ------------------------------------------------------------

def create(db, user, **fields):
    return create_course(db, user.id, CourseCreate(code="CPSC 221", name="Algorithms", year=2,
                                                   semester="Fall", **fields))


def test_it_is_optional(db, user):
    assert create(db, user).section is None


def test_a_blank_section_is_no_section(db, user):
    course = create(db, user, section="  ")
    assert course.section is None


def test_it_is_stored_trimmed(db, user):
    assert create(db, user, section=" L2B ").section == "L2B"


def test_an_edit_that_does_not_mention_it_keeps_it(db, user):
    """A validator that assigns a field marks it as sent; an edit of the name
    must not clear the section on the way through."""
    course = create(db, user, section="101")
    edited = update_course(db, user.id, course.id, CourseUpdate(name="Renamed"))
    assert (edited.name, edited.section) == ("Renamed", "101")


def test_it_can_be_changed_and_cleared(db, user):
    course = create(db, user, section="101")
    assert update_course(db, user.id, course.id, CourseUpdate(section="102")).section == "102"
    assert update_course(db, user.id, course.id, CourseUpdate(section="")).section is None


def test_it_is_capped():
    with pytest.raises(ValueError):
        CourseUpdate(section="x" * 21)


# --- the routes ------------------------------------------------------------

@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_routes_carry_it(db, user, client):
    body = {"code": "CPSC 221", "name": "Algorithms", "year": 2, "semester": "Fall", "section": "101"}
    made = client.post(f"/api/grades/{user.id}/courses", json=body)
    assert made.status_code in (200, 201), made.text
    course_id = made.json()["id"]
    assert made.json()["section"] == "101"
    edited = client.patch(f"/api/grades/{user.id}/courses/{course_id}", json={"section": "L2B"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["section"] == "L2B"
