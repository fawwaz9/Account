"""The next-term planner (Phase 4 item 12, §13.6).

Pinned: figures read through the floor exactly as the course page reads them,
so nothing below it shows here; hours summed over the courses that have them,
the rest named rather than counted as zero; catalogue courses only, no repeats;
nothing written.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.identity import act_as
from app._database.models import COHORT_FLOOR, CatalogueCourseModel, CourseIntelModel
from app.Auth.dependencies import get_current_user
from app.Grades.schemas.next_term import NextTermIn
from app.Grades.services.next_term_service import next_term


@pytest.fixture(autouse=True)
def signed_in(db, user):
    """On Postgres the figures are read through a definer function that answers only
    a signed-in caller, as every request is in the app (get_current_user acts as the
    user first); the tests act as the user the same way."""
    act_as(db, user.id)


def catalogue(db, subject, number, campus="UBCV", credits=3.0, title=None):
    row = CatalogueCourseModel(id=uuid.uuid4(), campus=campus, subject=subject, number=number,
                               title=title or f"{subject} {number}", credits=credits)
    db.add(row)
    db.commit()
    return row


def intel(db, key, hours=None, answers=COHORT_FLOOR, difficulty=None):
    db.add(CourseIntelModel(id=uuid.uuid4(), course_key=key, hours_answers=answers, hours_median=hours,
                            difficulty_answers=answers if difficulty is not None else None,
                            difficulty_mean=difficulty))
    db.commit()


@pytest.fixture
def three(db):
    a = catalogue(db, "CPSC", "221", credits=4.0)
    b = catalogue(db, "MATH", "200")
    c = catalogue(db, "PHIL", "220")
    intel(db, "UBCV CPSC 221", hours=12.0, difficulty=4.0)
    intel(db, "UBCV MATH 200", hours=8.5, difficulty=3.0)
    return a, b, c


def test_hours_add_up_over_the_courses_that_have_them(db, user, three):
    plan = next_term(db, user.id, NextTermIn(catalogue_ids=[c.id for c in three]))

    assert plan.total_hours == 20.5 and plan.courses_with_hours == 2
    assert plan.mean_difficulty == 3.5
    assert plan.total_credits == 10.0
    assert plan.missing == ["PHIL 220"]
    assert any("not counted as zero" in a for a in plan.assumptions)


def test_courses_come_back_in_the_order_given(db, user, three):
    a, b, c = three
    plan = next_term(db, user.id, NextTermIn(catalogue_ids=[c.id, a.id, b.id]))

    assert [x.code for x in plan.courses] == ["PHIL 220", "CPSC 221", "MATH 200"]


def test_a_figure_below_the_floor_never_shows(db, user):
    row = catalogue(db, "STAT", "200")
    intel(db, "UBCV STAT 200", hours=30.0, answers=COHORT_FLOOR - 1, difficulty=5.0)

    plan = next_term(db, user.id, NextTermIn(catalogue_ids=[row.id]))

    assert plan.courses[0].intel is None
    assert plan.total_hours is None and plan.mean_difficulty is None and plan.missing == ["STAT 200"]


def test_the_campus_is_part_of_the_key(db, user):
    okanagan = catalogue(db, "CPSC", "221", campus="UBCO")
    intel(db, "UBCV CPSC 221", hours=12.0)

    plan = next_term(db, user.id, NextTermIn(catalogue_ids=[okanagan.id]))

    assert plan.courses[0].intel is None


def test_only_catalogue_courses(db, user, three):
    with pytest.raises(ValueError):
        next_term(db, user.id, NextTermIn(catalogue_ids=[three[0].id, uuid.uuid4()]))


def test_no_repeats(db, user, three):
    with pytest.raises(ValueError):
        next_term(db, user.id, NextTermIn(catalogue_ids=[three[0].id, three[0].id]))


@pytest.mark.parametrize("ids", [[], [uuid.uuid4() for _ in range(9)]])
def test_one_to_eight_courses(ids):
    with pytest.raises(ValueError):
        NextTermIn(catalogue_ids=ids)


@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_route(db, user, three, client):
    url = f"/api/grades/{user.id}/next-term"

    body = client.post(url, json={"catalogue_ids": [str(c.id) for c in three]}).json()
    assert body["total_hours"] == 20.5 and body["floor"] == COHORT_FLOOR
    assert client.post(url, json={"catalogue_ids": [str(uuid.uuid4())]}).status_code == 422
    assert client.post(url, json={"catalogue_ids": []}).status_code == 422
