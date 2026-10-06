"""Linking your courses to the shared catalogue (Phase 2 item 3, D11).

Automatic by campus and code, computed on read; overridden by a course you
pick or by "none". And the property the plan's "Done when" names: linking moves
no grade, average or credit anywhere.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import CatalogueCourseModel, GradeModel
from app.Auth.dependencies import get_current_user
from app.Grades.services.catalogue_service import key_of, match
from conftest import make_course, make_user


def catalogue(db, campus, subject, number, title=None):
    row = CatalogueCourseModel(id=uuid.uuid4(), campus=campus, subject=subject, number=number, title=title)
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def link_url(user, course):
    return f"/api/grades/{user.id}/courses/{course.id}/catalogue"


# --- reading a code ----------------------------------------------------------

@pytest.mark.parametrize(("code", "expected"), [
    ("CPSC_V 110", ("UBCV", "CPSC", "110")),
    ("COSC_O 111", ("UBCO", "COSC", "111")),
    ("cpsc_v110", ("UBCV", "CPSC", "110")),
    ("CPSC 110", (None, "CPSC", "110")),
    ("ENGL 100A", (None, "ENGL", "100A")),
    ("CPSC_X 110", (None, "CPSC", "110")),
])
def test_a_code_names_its_campus_by_suffix(code, expected):
    key = key_of(code)
    assert (key.campus, key.subject, key.number) == expected


@pytest.mark.parametrize("code", ["", "Intro to CS", "CPSC", "110", "CPSC 11"])
def test_what_is_not_a_code_names_nothing(code):
    assert key_of(code) is None


# --- matching ----------------------------------------------------------------

def test_a_suffixed_code_matches_its_own_campus_only(db):
    vancouver = catalogue(db, "UBCV", "CPSC", "110")
    catalogue(db, "UBCO", "CPSC", "110")
    assert match(db, "CPSC_V 110").id == vancouver.id


def test_a_code_two_campuses_share_matches_nothing_without_a_suffix(db):
    catalogue(db, "UBCV", "CPSC", "110")
    catalogue(db, "UBCO", "CPSC", "110")
    assert match(db, "CPSC 110") is None


def test_a_code_one_campus_offers_matches_without_a_suffix(db):
    only = catalogue(db, "UBCO", "COSC", "111")
    assert match(db, "cosc 111").id == only.id


# --- the link, through the API -------------------------------------------------

def test_a_course_links_itself_once_the_catalogue_has_it(db, user, client):
    course = make_course(db, user.id, "CPSC_V 221")
    assert client.get(link_url(user, course)).json() == {"how": "not_found", "course": None}

    row = catalogue(db, "UBCV", "CPSC", "221", "Basic Algorithms")
    body = client.get(link_url(user, course)).json()
    assert body["how"] == "matched" and body["course"]["id"] == str(row.id)


def test_a_choice_beats_the_match_and_survives_a_code_change(db, user, client):
    course = make_course(db, user.id, "CPSC_V 221")
    catalogue(db, "UBCV", "CPSC", "221")
    picked = catalogue(db, "UBCO", "COSC", "221")

    body = client.put(link_url(user, course), json={"mode": "chosen", "catalogue_course_id": str(picked.id)}).json()
    assert body["how"] == "chosen" and body["course"]["id"] == str(picked.id)

    client.patch(f"/api/grades/{user.id}/courses/{course.id}", json={"code": "CPSC_V 213"})
    assert client.get(link_url(user, course)).json()["course"]["id"] == str(picked.id)


def test_none_stays_none_when_the_catalogue_gains_the_course(db, user, client):
    course = make_course(db, user.id, "CPSC_V 221")
    assert client.put(link_url(user, course), json={"mode": "none"}).json() == {"how": "none_chosen", "course": None}
    catalogue(db, "UBCV", "CPSC", "221")
    assert client.get(link_url(user, course)).json()["how"] == "none_chosen"


def test_back_to_automatic(db, user, client):
    course = make_course(db, user.id, "CPSC_V 221")
    row = catalogue(db, "UBCV", "CPSC", "221")
    client.put(link_url(user, course), json={"mode": "none"})
    body = client.put(link_url(user, course), json={"mode": "auto"}).json()
    assert body["how"] == "matched" and body["course"]["id"] == str(row.id)


def test_a_chosen_course_that_has_gone_falls_back_to_matching(db, user, client):
    course = make_course(db, user.id, "CPSC_V 221")
    picked = catalogue(db, "UBCO", "COSC", "221")
    client.put(link_url(user, course), json={"mode": "chosen", "catalogue_course_id": str(picked.id)})
    db.delete(picked)
    db.commit()
    assert client.get(link_url(user, course)).json()["how"] == "not_found"


def test_choosing_what_is_not_in_the_catalogue_is_refused(db, user, client):
    course = make_course(db, user.id, "CPSC_V 221")
    response = client.put(link_url(user, course), json={"mode": "chosen", "catalogue_course_id": str(uuid.uuid4())})
    assert response.status_code == 404
    assert client.get(link_url(user, course)).json()["how"] == "not_found"


@pytest.mark.parametrize("body", [
    {"mode": "chosen"},
    {"mode": "none", "catalogue_course_id": str(uuid.uuid4())},
    {"mode": "auto", "catalogue_course_id": str(uuid.uuid4())},
])
def test_an_id_comes_exactly_with_chosen(db, user, client, body):
    course = make_course(db, user.id, "CPSC_V 221")
    assert client.put(link_url(user, course), json=body).status_code == 422


def test_one_persons_choice_is_theirs_alone(db, user, client):
    other = make_user(db, "other-link@example.com")
    mine = make_course(db, user.id, "CPSC_V 221")
    theirs = make_course(db, other.id, "CPSC_V 221")
    catalogue(db, "UBCV", "CPSC", "221")
    client.put(link_url(user, mine), json={"mode": "none"})
    db.refresh(theirs)
    assert theirs.catalogue_unlinked is False


def test_search_by_how_people_type_a_code(db, user, client):
    catalogue(db, "UBCV", "CPSC", "210")
    catalogue(db, "UBCV", "CPSC", "221")
    catalogue(db, "UBCO", "COSC", "221")
    catalogue(db, "UBCV", "MATH", "200")

    def codes(q):
        rows = client.get(f"/api/grades/{user.id}/catalogue", params={"q": q}).json()
        return [(r["campus"], r["subject"], r["number"]) for r in rows]

    assert codes("cpsc 2") == [("UBCV", "CPSC", "210"), ("UBCV", "CPSC", "221")]
    assert codes("221") == [("UBCO", "COSC", "221"), ("UBCV", "CPSC", "221")]
    assert codes("cosc_o") == [("UBCO", "COSC", "221")]
    assert codes("%") == []
    assert codes("c_") == []


# --- linking moves nothing ---------------------------------------------------

def test_linking_and_unlinking_move_no_grade_average_or_credit(db, user, client):
    """The plan's "Done when" for item 3: every figure the grades room shows,
    before and after each kind of link, identical."""
    past = make_course(db, user.id, "CPSC_V 110", year=1, final_grade=82.0)
    current = make_course(db, user.id, "CPSC_V 221", year=3)
    transfer = make_course(db, user.id, "MATH 100", transfer_credit=True, credits=6.0)
    db.add(GradeModel(id=uuid.uuid4(), course_id=current.id, name="A1", category="Assignment",
                      score=8.0, max_score=10.0, excluded=False))
    db.commit()
    rows = [catalogue(db, "UBCV", "CPSC", "110"), catalogue(db, "UBCV", "CPSC", "221")]
    other = catalogue(db, "UBCO", "MATH", "100")

    def read(url):
        # Not vacuous: two identical 404s would compare equal.
        response = client.get(url)
        assert response.status_code == 200, f"{url}: {response.status_code}"
        return response.json()

    def figures():
        return {
            "dashboard": read(f"/api/grades/{user.id}/grades/dashboard"),
            "courses": read(f"/api/grades/{user.id}/courses"),
            "detail": [read(f"/api/grades/{user.id}/courses/{c.id}") for c in (past, current, transfer)],
            "degree": read(f"/api/degree/{user.id}"),
        }

    before = figures()
    assert before["courses"] and before["dashboard"]

    for choice in ({"mode": "chosen", "catalogue_course_id": str(other.id)}, {"mode": "none"}, {"mode": "auto"}):
        for course in (past, current, transfer):
            assert client.put(link_url(user, course), json=choice).status_code == 200
        assert figures() == before, f"a figure moved after linking with {choice['mode']}"
    _ = rows
