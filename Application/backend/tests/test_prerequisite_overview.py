"""The degree audit's prerequisites list: each course under way or planned, in a word.

Prerequisites moved off the course page to the Degree page (owner, 2026-11-07). The
page lists the courses whose rules aren't met or are only on track, and the rest on
request; each course's rules are still read and changed at its own route.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import CatalogueCourseModel, CataloguePrerequisiteModel
from app.Auth.dependencies import get_current_user
from app.Grades.services.prerequisite_service import overview
from conftest import make_course, make_user


@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def rule(client, user, course, text, kind="prerequisite"):
    response = client.put(f"/api/grades/{user.id}/courses/{course.id}/prerequisites", json={"text": text, "kind": kind})
    assert response.status_code == 200, response.text


def by_code(summaries):
    return {s.code if hasattr(s, "code") else s["code"]: s for s in summaries}


def test_each_course_under_way_reads_as_its_worst_rule(db, user, client):
    make_course(db, user.id, "CPSC_V 110", year=1, final_grade=82.0)
    met = make_course(db, user.id, "CPSC_V 210", year=2)
    missing = make_course(db, user.id, "CPSC_V 221", year=3)
    mixed = make_course(db, user.id, "CPSC_V 213", year=3)
    rule(client, user, met, "CPSC 110")
    rule(client, user, missing, "CPSC 999")
    rule(client, user, mixed, "CPSC 110")
    rule(client, user, mixed, "MATH 999", kind="corequisite")

    found = by_code(overview(db, user.id))
    assert found["CPSC_V 210"].status == "met"
    assert found["CPSC_V 221"].status == "not_met"
    assert found["CPSC_V 213"].status == "not_met", "the worst rule decides"


def test_a_course_with_no_rule_says_none(db, user):
    make_course(db, user.id, "ENGL 100", year=1)
    found = by_code(overview(db, user.id))
    assert found["ENGL 100"].status is None
    assert found["ENGL 100"].linked is False


def test_the_shared_rule_counts_when_you_have_none_and_marks_the_course_linked(db, user):
    catalogue = CatalogueCourseModel(id=uuid.uuid4(), campus="UBCV", subject="CPSC", number="221")
    db.add(catalogue)
    db.flush()
    db.add(CataloguePrerequisiteModel(id=uuid.uuid4(), catalogue_course_id=catalogue.id, kind="prerequisite",
                                      session="2026W", rule={"course": "CPSC 210"}, source="reviewed-proposal"))
    db.commit()
    make_course(db, user.id, "CPSC_V 221", year=3)

    found = by_code(overview(db, user.id))
    assert found["CPSC_V 221"].linked is True
    assert found["CPSC_V 221"].status == "not_met"


def test_finished_and_archived_courses_are_left_out_and_later_terms_are_planned(db, user):
    user.current_school_year, user.current_semester = 2, "Fall"
    db.commit()
    make_course(db, user.id, "CPSC_V 110", year=1, final_grade=82.0)
    make_course(db, user.id, "CPSC_V 121", year=2, archived=True)
    make_course(db, user.id, "CPSC_V 210", year=2)
    make_course(db, user.id, "CPSC_V 221", year=3)

    found = by_code(overview(db, user.id))
    assert set(found) == {"CPSC_V 210", "CPSC_V 221"}
    assert found["CPSC_V 210"].planned is False
    assert found["CPSC_V 221"].planned is True


def test_the_route_answers_for_the_caller_only(db, user, client):
    other = make_user(db, "someone-else@example.com")
    make_course(db, user.id, "CPSC_V 221", year=3)
    make_course(db, other.id, "MATH 200", year=3)

    body = client.get(f"/api/degree/{user.id}/prerequisites").json()
    assert [row["code"] for row in body] == ["CPSC_V 221"]
    assert set(body[0]) == {"course_id", "code", "name", "planned", "status", "linked"}
    assert client.get(f"/api/degree/{other.id}/prerequisites").status_code in (403, 404)
