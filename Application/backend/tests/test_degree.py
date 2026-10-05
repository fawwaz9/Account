"""The degree audit (Phase 1 item 5, D31), against hand-worked programmes.

Your requirements and mappings are entered once; the audit reads your courses
with the dashboard's term rule. What it must get right, each pinned below:
alternatives, patterns, credits taken only until a bucket is met, no course
counted twice unless a requirement shares, mappings that replace their
sources (many-to-one only when every source is done; one-to-many meeting
several items), partial credit, and courses that did not pass counting nowhere.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app.Auth.dependencies import get_current_user
from app.Grades.schemas.degree import EquivalenceWrite, RequirementWrite
from app.Grades.services.degree_service import (
    audit,
    create_equivalence,
    create_requirement,
    delete_equivalence,
    delete_requirement,
    update_requirement,
)
from conftest import make_course, make_user


@pytest.fixture
def me(db, user):
    """In year 3 Fall: year 2 is past, year 3 Fall current, year 4 future."""
    user.current_school_year, user.current_semester = 3, "Fall"
    db.commit()
    return user


def past(db, user, code, credits=3.0, final=80.0, **kw):
    return make_course(db, user.id, code, year=2, semester="Fall", credits=credits, final_grade=final, **kw)


def current(db, user, code, credits=3.0, **kw):
    return make_course(db, user.id, code, year=3, semester="Fall", credits=credits, **kw)


def future(db, user, code, credits=3.0):
    return make_course(db, user.id, code, year=4, semester="Fall", credits=credits)


def need(db, user, name, kind, items, credits=None, shares=False):
    return create_requirement(db, user.id, RequirementWrite(
        name=name, kind=kind, items=items, credits_needed=credits, shares=shares))


def maps(db, user, from_codes, counts_as, credits=None):
    return create_equivalence(db, user.id, EquivalenceWrite(from_codes=from_codes, counts_as=counts_as, credits=credits))


def result(db, user, name):
    return next(r for r in audit(db, user.id).requirements if r.requirement.name == name)


# --- requirements ----------------------------------------------------------

def test_an_item_may_name_alternatives(db, me):
    past(db, me, "MATH 180")
    need(db, me, "Calculus", "courses", ["MATH 100 | MATH 180"])
    r = result(db, me, "Calculus")
    assert r.items[0].met_by.label == "MATH 180" and r.done


def test_a_missing_item_is_said_and_in_progress_is_not_done(db, me):
    past(db, me, "CPSC 110")
    current(db, me, "CPSC 210")
    need(db, me, "Core", "courses", ["CPSC 110", "CPSC 210", "CPSC 221"])
    r = result(db, me, "Core")
    assert [(i.item, i.met_by.status if i.met_by else None) for i in r.items] == [
        ("CPSC 110", "completed"), ("CPSC 210", "in_progress"), ("CPSC 221", None)]
    assert not r.done and (r.credits_completed, r.credits_in_progress) == (3.0, 3.0)


def test_a_credits_bucket_takes_completed_first_and_only_what_it_needs(db, me):
    """The in-progress CPSC 301 sorts first by name; completed still wins."""
    current(db, me, "CPSC 301")
    past(db, me, "CPSC 310")
    past(db, me, "CPSC 320")
    need(db, me, "Upper CPSC", "credits", ["CPSC 3xx"], credits=6)
    need(db, me, "More upper", "credits", ["CPSC 300+"], credits=3)
    first, second = result(db, me, "Upper CPSC"), result(db, me, "More upper")
    assert sorted(c.label for c in first.counted) == ["CPSC 310", "CPSC 320"] and first.done
    assert [c.label for c in second.counted] == ["CPSC 301"] and not second.done


def test_patterns_reach_any_subject_and_whole_subjects(db, me):
    past(db, me, "ENGL 110")
    past(db, me, "STAT 302")
    need(db, me, "Upper anything", "credits", ["300+"], credits=3)
    need(db, me, "Any English", "credits", ["ENGL"], credits=3)
    assert [c.label for c in result(db, me, "Upper anything").counted] == ["STAT 302"]
    assert [c.label for c in result(db, me, "Any English").counted] == ["ENGL 110"]


def test_a_course_counts_once_unless_a_requirement_shares(db, me):
    past(db, me, "BIOL 111")
    need(db, me, "Science core", "courses", ["BIOL 111"])
    need(db, me, "Science electives", "credits", ["BIOL"], credits=3)
    need(db, me, "Breadth: science", "credits", ["BIOL"], credits=3, shares=True)
    assert result(db, me, "Science core").done
    assert result(db, me, "Science electives").counted == []
    assert result(db, me, "Breadth: science").done


def test_courses_requirements_are_filled_before_credits_ones(db, me):
    """Entered credits-first, the specific requirement still gets its course."""
    past(db, me, "CPSC 310")
    need(db, me, "Electives", "credits", ["CPSC 3xx"], credits=3)
    need(db, me, "Software engineering", "courses", ["CPSC 310"])
    assert result(db, me, "Software engineering").done
    assert not result(db, me, "Electives").done


# --- equivalences ----------------------------------------------------------

def test_two_courses_count_as_one_only_once_both_are_on_the_record(db, me):
    past(db, me, "COSC 111")
    maps(db, me, ["COSC 111", "COSC 121"], ["CPSC 110"])
    need(db, me, "Intro", "courses", ["CPSC 110"])
    assert result(db, me, "Intro").items[0].met_by is None  # COSC 121 missing
    current(db, me, "COSC 121")
    met = result(db, me, "Intro").items[0].met_by
    assert (met.label, met.status, met.credits) == ("COSC 111 + COSC 121 as CPSC 110", "in_progress", 6.0)


def test_one_course_can_count_as_several(db, me):
    past(db, me, "COSC 211")
    maps(db, me, ["COSC 211"], ["CPSC 121", "CPSC 213"])
    need(db, me, "Systems", "courses", ["CPSC 121", "CPSC 213"])
    r = result(db, me, "Systems")
    assert r.done and r.credits_completed == 3.0  # one course's credits, counted once


def test_partial_credit_and_no_double_counting_of_the_source(db, me):
    past(db, me, "PHYS 1XX", credits=4.0)
    past(db, me, "MATH 1ZZ")  # unparseable codes are simply not counted
    past(db, me, "COSC 122", credits=3.0)
    maps(db, me, ["COSC 122"], ["CPSC 103"], credits=1.5)
    need(db, me, "Computing", "credits", ["CPSC"], credits=1.5)
    need(db, me, "Anything COSC", "credits", ["COSC"], credits=3)
    assert result(db, me, "Computing").credits_completed == 1.5 and result(db, me, "Computing").done
    assert result(db, me, "Anything COSC").counted == []  # COSC 122 was replaced by the mapping


# --- what counts at all ----------------------------------------------------

def test_a_course_that_did_not_pass_counts_nowhere(db, me):
    past(db, me, "MATH 200", final=45.0)
    need(db, me, "Math", "courses", ["MATH 200"])
    full = audit(db, me.id)
    assert full.failed == ["MATH 200"] and full.requirements[0].items[0].met_by is None
    assert full.credits_completed == 0.0


def test_a_retake_counts_the_pass(db, me):
    past(db, me, "MATH 200", final=45.0)
    current(db, me, "MATH 200 ", final_grade=72.0)
    need(db, me, "Math", "courses", ["MATH 200"])
    met = audit(db, me.id).requirements[0].items[0].met_by
    assert met.status == "completed"


@pytest.mark.parametrize("planned_first", [True, False])
def test_of_two_rows_for_one_code_the_more_finished_counts(db, me, planned_first):
    """Taken, and on the plan again (to raise the grade): it is completed,
    whichever row the courses list happens to give first."""
    if planned_first:
        future(db, me, "CPSC 110")
        past(db, me, "CPSC 110 ")
    else:
        past(db, me, "CPSC 110")
        future(db, me, "CPSC 110 ")
    need(db, me, "Intro", "courses", ["CPSC 110"])
    assert result(db, me, "Intro").items[0].met_by.status == "completed"


def test_transfer_credit_planned_and_archived(db, me):
    make_course(db, me.id, "ASTR 101", year=1, semester="Fall", transfer_credit=True, final_grade=0.0)
    future(db, me, "CPSC 410")
    past(db, me, "FREN 101", archived=True)
    need(db, me, "Science", "credits", ["ASTR"], credits=3)
    need(db, me, "Capstone", "courses", ["CPSC 410"])
    need(db, me, "Language", "credits", ["FREN"], credits=3)
    assert result(db, me, "Science").done
    assert result(db, me, "Capstone").items[0].met_by.status == "planned"
    assert result(db, me, "Language").counted == []


def test_totals_and_what_counted_toward_nothing(db, me):
    past(db, me, "CPSC 110")
    past(db, me, "MUSC 100")
    current(db, me, "CPSC 210", credits=4.0)
    need(db, me, "Intro", "courses", ["CPSC 110"])
    full = audit(db, me.id)
    assert (full.credits_completed, full.credits_in_progress, full.credit_target) == (6.0, 4.0, 120)
    assert [c.label for c in full.not_counted] == ["MUSC 100"]


# --- validation, ownership and routes --------------------------------------

@pytest.mark.parametrize("items, message", [
    (["CPSC 11"], "not a course code or pattern"),
    (["nonsense here"], "not a course code or pattern"),
    (["  "], "at least one"),
])
def test_unreadable_items_are_refused_with_the_forms_that_work(items, message):
    with pytest.raises(ValueError, match=message):
        RequirementWrite(name="x", kind="courses", items=items)


def test_a_credits_requirement_needs_a_number():
    with pytest.raises(ValueError, match="how many credits"):
        RequirementWrite(name="x", kind="credits", items=["CPSC"])


def test_someone_elses_rows_are_not_found(db, me):
    mine = need(db, me, "Mine", "courses", ["CPSC 110"])
    mapping = maps(db, me, ["COSC 111"], ["CPSC 110"])
    other = make_user(db, "other@example.com")
    edit = RequirementWrite(name="x", kind="courses", items=["CPSC 110"])
    assert update_requirement(db, other.id, mine.id, edit) is None
    assert delete_requirement(db, other.id, mine.id) is False
    assert delete_equivalence(db, other.id, mapping.id) is False
    assert audit(db, other.id).requirements == [] and audit(db, other.id).equivalences == []


@pytest.fixture
def client(db, me):
    app.main.app.dependency_overrides[get_current_user] = lambda: me
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_routes(db, me, client):
    past(db, me, "CPSC 110")
    base = f"/api/degree/{me.id}"
    made = client.post(f"{base}/requirements", json={"name": "Intro", "kind": "courses", "items": ["CPSC 110"]})
    assert made.status_code == 200
    assert client.get(base).json()["requirements"][0]["done"] is True
    bad = client.post(f"{base}/requirements", json={"name": "x", "kind": "courses", "items": ["CPSC 11"]})
    assert bad.status_code == 422
    rid = made.json()["id"]
    assert client.put(f"{base}/requirements/{rid}", json={"name": "Renamed", "kind": "courses",
                                                          "items": ["CPSC 110"]}).json()["name"] == "Renamed"
    eq = client.post(f"{base}/equivalences", json={"from_codes": ["COSC 111"], "counts_as": ["CPSC 110"]})
    assert eq.status_code == 200
    assert client.delete(f"{base}/equivalences/{eq.json()['id']}").json() == {"deleted": True}
    assert client.delete(f"{base}/requirements/{rid}").json() == {"deleted": True}
    assert client.delete(f"{base}/requirements/{uuid.uuid4()}").status_code == 404


def test_the_more_finished_row_wins_whatever_order_the_courses_come_in():
    """The courses list happens to come ordered by term; the audit must not
    depend on it."""
    from types import SimpleNamespace
    from app.Grades.services.degree_service import build_units

    def row(bucket, final=0.0):
        return SimpleNamespace(code="CPSC 110", credits=3.0, archived=False, transfer_credit=False,
                               term_bucket=bucket, final_grade=final, average=0.0)

    for rows in ([row("future"), row("past", 80.0)], [row("past", 80.0), row("future")]):
        units, failed = build_units(rows, [])
        assert [(u.label, u.status) for u in units] == [("CPSC 110", "completed")] and failed == []
