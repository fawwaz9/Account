"""Prerequisites: the rule language, met or not, yours and the shared one
(Phase 2 items 4 and 7, D12).

Advisory throughout (D3): every answer is met, on track or not met, and
nothing anywhere is refused because a rule is unmet.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import (
    CatalogueCourseModel, CataloguePrerequisiteModel, CourseEquivalenceModel, PrerequisiteProposalModel,
)
from app.Auth.dependencies import get_current_user
from app.Grades.utils.prerequisites import (
    MET, NOT_MET, ON_TRACK, RuleError, Taken, evaluate, parse_text, render, validate,
)
from conftest import make_course, make_user


# --- the typed form ----------------------------------------------------------

@pytest.mark.parametrize(("text", "rule"), [
    ("CPSC 210", {"course": "CPSC 210"}),
    ("cpsc_v 210", {"course": "CPSC 210"}),
    ("CPSC 210 with 64%", {"course": "CPSC 210", "min_grade": 64.0}),
    ("CPSC 210 (64%)", {"course": "CPSC 210", "min_grade": 64.0}),
    ("CPSC 210 and one of MATH 200, MATH 217",
     {"all": [{"course": "CPSC 210"}, {"any": [{"course": "MATH 200"}, {"course": "MATH 217"}]}]}),
    ("CPSC 121 or MATH 220 and MATH 100",
     {"all": [{"any": [{"course": "CPSC 121"}, {"course": "MATH 220"}]}, {"course": "MATH 100"}]}),
    ("CPSC 121 or (MATH 220 and MATH 100)",
     {"any": [{"course": "CPSC 121"}, {"all": [{"course": "MATH 220"}, {"course": "MATH 100"}]}]}),
    ("6 credits of MATH 1xx", {"credits": 6.0, "subject": "MATH", "level": 100}),
    ("24 credits", {"credits": 24.0}),
    ("3 credits of 3xx", {"credits": 3.0, "level": 300}),
    ("CPSC 110, MATH 100", {"all": [{"course": "CPSC 110"}, {"course": "MATH 100"}]}),
    ("all of CPSC 110, CPSC 121", {"all": [{"course": "CPSC 110"}, {"course": "CPSC 121"}]}),
    ("ENGL 100A", {"course": "ENGL 100A"}),
])
def test_the_typed_form_reads_as_people_write_it(text, rule):
    assert parse_text(text) == rule


@pytest.mark.parametrize("text", [
    "CPSC 210 and one of MATH 200, MATH 217",
    "(CPSC 121 or MATH 220) and 6 credits of MATH 1xx",
    "CPSC 110 with 70% or CPSC 103",
    "CPSC 121 or (MATH 220 and MATH 100)",
    "one of CPSC 110, CPSC 103 and MATH 100",
    "24 credits",
])
def test_render_reads_back_to_the_same_tree(text):
    rule = parse_text(text)
    assert parse_text(render(rule)) == rule


@pytest.mark.parametrize("text", [
    "", "   ", "permission of the instructor", "CPSC", "(CPSC 210", "CPSC 210)", "CPSC 210 and",
    "CPSC 210 with", "CPSC 210 with 0%", "CPSC 210 with 150%", "x" * 301,
])
def test_what_cannot_be_read_is_refused_with_a_reason(text):
    with pytest.raises(RuleError):
        parse_text(text)


@pytest.mark.parametrize("rule", [
    {}, [], "CPSC 210", {"course": "nope"}, {"course": 210}, {"course": "CPSC 210", "extra": 1},
    {"credits": 0}, {"credits": True}, {"credits": 3, "level": 150}, {"credits": 3, "subject": "M4TH"},
    {"all": []}, {"any": "CPSC 210"}, {"all": [{"course": "CPSC 110"}] * 13},
    {"all": [{"any": [{"all": [{"any": [{"all": [{"course": "CPSC 110"}] * 2}] * 2}] * 2}] * 2}] * 2},
    {"course": "CPSC 210", "min_grade": "64"},
])
def test_a_bad_tree_is_refused(rule):
    with pytest.raises(RuleError):
        validate(rule)


def test_a_group_of_one_is_just_the_one():
    assert validate({"all": [{"course": "cpsc 110"}]}) == {"course": "CPSC 110"}


# --- met, on track, not met --------------------------------------------------

FALL_Y2, WINTER_Y2, FALL_Y3 = (2, 0), (2, 1), (3, 0)


def taken(code, status="completed", term=FALL_Y2, grade=80.0, credits=3.0):
    subject, number = code.split(" ")
    return Taken(label=code, codes=frozenset({(subject, int(number))}), credits=credits,
                 status=status, term=term, grade=grade)


def status_of(text, record, term=FALL_Y3, kind="prerequisite"):
    return evaluate(parse_text(text), record, term, kind).status


def test_a_course_done_before_is_met():
    assert status_of("CPSC 210", [taken("CPSC 210")]) == MET


def test_a_course_not_on_the_record_is_not_met():
    result = evaluate(parse_text("CPSC 210"), [], FALL_Y3)
    assert result.status == NOT_MET and "not on your record" in result.detail


def test_a_course_in_progress_before_is_on_track():
    assert status_of("CPSC 210", [taken("CPSC 210", "in_progress", WINTER_Y2, None)]) == ON_TRACK


def test_a_prerequisite_in_the_same_term_is_not_met_but_a_corequisite_is_fine():
    same_term = [taken("CPSC 210", "in_progress", FALL_Y3, None)]
    assert status_of("CPSC 210", same_term) == NOT_MET
    assert status_of("CPSC 210", same_term, kind="corequisite") == ON_TRACK


def test_a_prerequisite_taken_later_does_not_count():
    assert status_of("CPSC 210", [taken("CPSC 210", term=(4, 0))]) == NOT_MET


def test_a_minimum_grade_is_checked_when_the_result_is_known():
    assert status_of("CPSC 210 with 64%", [taken("CPSC 210", grade=70.0)]) == MET
    result = evaluate(parse_text("CPSC 210 with 64%"), [taken("CPSC 210", grade=60.0)], FALL_Y3)
    assert result.status == NOT_MET and "64% needed" in result.detail


def test_a_transfer_credit_meets_a_minimum_grade_it_has_no_grade_for():
    assert status_of("CPSC 210 with 64%", [taken("CPSC 210", grade=None)]) == MET


def test_a_course_not_passed_is_not_met():
    result = evaluate(parse_text("CPSC 210"), [taken("CPSC 210", "failed", grade=40.0)], FALL_Y3)
    assert result.status == NOT_MET and "not passed" in result.detail


def test_any_takes_the_best_and_all_the_worst():
    record = [taken("MATH 200"), taken("CPSC 210", "in_progress", WINTER_Y2, None)]
    assert status_of("MATH 200 or MATH 217", record) == MET
    assert status_of("CPSC 210 and MATH 200", record) == ON_TRACK
    assert status_of("CPSC 210 and MATH 217", record) == NOT_MET


def test_credits_count_what_is_done_and_what_is_coming():
    record = [taken("MATH 100"), taken("MATH 101", "in_progress", WINTER_Y2, None), taken("CPSC 110")]
    assert status_of("3 credits of MATH 1xx", record) == MET
    assert status_of("6 credits of MATH 1xx", record) == ON_TRACK
    result = evaluate(parse_text("9 credits of MATH"), record, FALL_Y3)
    assert result.status == NOT_MET and result.detail.startswith("3 of 9 credits")
    assert status_of("9 credits", record) == ON_TRACK


# --- through the API ---------------------------------------------------------

@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def url(user, course):
    return f"/api/grades/{user.id}/courses/{course.id}/prerequisites"


def shared(db, code="CPSC 221", campus="UBCV", rule=None, session="2026W", source="reviewed-proposal",
           source_text=None, kind="prerequisite"):
    subject, number = code.split(" ")
    course = db.query(CatalogueCourseModel).filter_by(campus=campus, subject=subject, number=number).first()
    if course is None:
        course = CatalogueCourseModel(id=uuid.uuid4(), campus=campus, subject=subject, number=number)
        db.add(course)
        db.flush()
    db.add(CataloguePrerequisiteModel(id=uuid.uuid4(), catalogue_course_id=course.id, kind=kind,
                                      session=session, rule=rule or {"course": "CPSC 210"}, source=source,
                                      source_text=source_text))
    db.commit()
    return course


def kind_of(body, kind="prerequisite"):
    return next(k for k in body["kinds"] if k["kind"] == kind)


def test_your_own_rule_applies_to_you_at_once(db, user, client):
    make_course(db, user.id, "CPSC_V 210", year=2, final_grade=82.0)
    course = make_course(db, user.id, "CPSC_V 221", year=3)
    body = client.put(url(user, course), json={"text": "cpsc 210 and math 200"}).json()
    entry = kind_of(body)
    assert entry["applies"] == "yours"
    assert entry["yours"]["text"] == "CPSC 210 and MATH 200"
    assert entry["yours"]["source"] == "typed" and entry["yours"]["review"] == "pending"
    assert entry["yours"]["result"]["status"] == "not_met"
    assert [p["status"] for p in entry["yours"]["result"]["parts"]] == ["met", "not_met"]


def test_the_shared_rule_applies_when_you_have_none_and_yours_wins_when_you_do(db, user, client):
    make_course(db, user.id, "CPSC_V 210", year=2, final_grade=82.0)
    course = make_course(db, user.id, "CPSC_V 221", year=3)
    shared(db, rule={"course": "CPSC 210"})

    entry = kind_of(client.get(url(user, course)).json())
    assert entry["applies"] == "shared" and entry["yours"] is None
    assert entry["shared"]["source"] == "reviewed" and entry["shared"]["result"]["status"] == "met"
    assert entry["shared"]["source_text"] is None

    entry = kind_of(client.put(url(user, course), json={"text": "CPSC 213"}).json())
    assert entry["applies"] == "yours"
    assert entry["shared"]["text"] == "CPSC 210"


def test_a_calendar_row_shows_its_own_wording(db, user, client):
    course = make_course(db, user.id, "CPSC_V 221", year=3)
    shared(db, source="ubc-calendar", source_text="Prerequisite: CPSC 210.")
    assert kind_of(client.get(url(user, course)).json())["shared"]["source_text"] == "Prerequisite: CPSC 210."


def test_the_rule_for_the_courses_own_session_is_picked(db, user, client):
    user.first_year_calendar_year = 2023
    db.commit()
    course = make_course(db, user.id, "CPSC_V 221", year=3, semester="Fall")  # 2025W
    shared(db, rule={"course": "CPSC 110"}, session="2024W")
    shared(db, rule={"course": "CPSC 210"}, session="2026W")
    assert kind_of(client.get(url(user, course)).json())["shared"]["text"] == "CPSC 110"

    user.first_year_calendar_year = None
    db.commit()
    assert kind_of(client.get(url(user, course)).json())["shared"]["text"] == "CPSC 210"


def test_your_courses_answer_correctly_including_a_transfer_credit(db, user, client):
    """Item 7's "Done when": your own record, with a transfer credit among it."""
    make_course(db, user.id, "MATH 100", year=1, transfer_credit=True, credits=6.0)
    make_course(db, user.id, "CPSC_V 110", year=1, final_grade=45.0)
    make_course(db, user.id, "CPSC_V 103", year=1, final_grade=75.0)
    course = make_course(db, user.id, "CPSC_V 210", year=2)
    entry = kind_of(client.put(url(user, course), json={"text": "MATH 100 with 60% and (CPSC 110 or CPSC 103)"}).json())
    result = entry["yours"]["result"]
    assert result["status"] == "met"
    math, either = result["parts"]
    assert math["status"] == "met"
    assert [p["status"] for p in either["parts"]] == ["not_met", "met"]
    assert "not passed" in either["parts"][0]["detail"]


def test_an_equivalence_meets_what_it_counts_as(db, user, client):
    make_course(db, user.id, "COSC_O 111", year=1, final_grade=80.0)
    db.add(CourseEquivalenceModel(id=uuid.uuid4(), user_id=user.id, from_codes=["COSC 111"],
                                  counts_as=["CPSC 110"]))
    db.commit()
    course = make_course(db, user.id, "CPSC_V 210", year=2)
    entry = kind_of(client.put(url(user, course), json={"text": "CPSC 110"}).json())
    assert entry["yours"]["result"]["status"] == "met"


def test_editing_your_rule_puts_it_back_to_pending(db, user, client):
    course = make_course(db, user.id, "CPSC_V 221", year=3)
    client.put(url(user, course), json={"text": "CPSC 210"})
    row = db.query(PrerequisiteProposalModel).filter_by(course_id=course.id).one()
    row.status = "accepted"
    db.commit()
    entry = kind_of(client.put(url(user, course), json={"text": "CPSC 213"}).json())
    assert entry["yours"]["review"] == "pending"
    assert db.query(PrerequisiteProposalModel).filter_by(course_id=course.id).count() == 1


def test_a_corequisite_is_its_own_rule(db, user, client):
    course = make_course(db, user.id, "CPSC_V 221", year=3)
    body = client.put(url(user, course), json={"kind": "corequisite", "text": "CPSC 213"}).json()
    assert kind_of(body)["yours"] is None
    assert kind_of(body, "corequisite")["yours"]["text"] == "CPSC 213"


def test_deleting_your_rule_leaves_the_shared_one(db, user, client):
    course = make_course(db, user.id, "CPSC_V 221", year=3)
    shared(db)
    client.put(url(user, course), json={"text": "CPSC 213"})
    entry = kind_of(client.delete(url(user, course), params={"kind": "prerequisite"}).json())
    assert entry["yours"] is None and entry["applies"] == "shared"


def test_one_persons_rule_never_reaches_another(db, user, client):
    other = make_user(db, "other-prereq@example.com")
    mine = make_course(db, user.id, "CPSC_V 221", year=3)
    theirs = make_course(db, other.id, "CPSC_V 221", year=3)
    client.put(url(user, mine), json={"text": "CPSC 213"})
    app.main.app.dependency_overrides[get_current_user] = lambda: other
    body = client.get(url(other, theirs)).json()
    assert all(k["yours"] is None and k["shared"] is None for k in body["kinds"])


def test_an_unreadable_rule_is_a_400_and_changes_nothing(db, user, client):
    course = make_course(db, user.id, "CPSC_V 221", year=3)
    response = client.put(url(user, course), json={"text": "permission of the instructor"})
    assert response.status_code == 400
    assert db.query(PrerequisiteProposalModel).count() == 0


def test_check_reads_a_rule_back(db, user, client):
    body = client.post(f"/api/grades/{user.id}/prerequisites/check", json={"text": "cpsc 210, math 200"}).json()
    assert body == {"rule": {"all": [{"course": "CPSC 210"}, {"course": "MATH 200"}]},
                    "text": "CPSC 210 and MATH 200"}
    bad = client.post(f"/api/grades/{user.id}/prerequisites/check", json={"text": "CPSC"})
    assert bad.status_code == 400


def test_an_unmet_rule_blocks_nothing(db, user, client):
    """D3: adding grades to, editing and re-terming a course whose rule is unmet
    all go through."""
    course = make_course(db, user.id, "CPSC_V 221", year=3)
    client.put(url(user, course), json={"text": "CPSC 210"})
    assert kind_of(client.get(url(user, course)).json())["yours"]["result"]["status"] == "not_met"
    assert client.patch(f"/api/grades/{user.id}/courses/{course.id}", json={"year": 4}).status_code == 200
    created = client.post(f"/api/grades/{user.id}/courses/{course.id}/grades", json={
        "name": "A1", "category": "Assignment", "score": 8, "max_score": 10})
    assert created.status_code == 200


def test_a_course_does_not_meet_its_own_rule(db, user, client):
    """A co-requisite may be taken the same term -- but not by being the course itself."""
    course = make_course(db, user.id, "CPSC_V 221", year=3)
    entry = kind_of(client.put(url(user, course), json={"kind": "corequisite", "text": "CPSC 221"}).json(),
                    "corequisite")
    assert entry["yours"]["result"]["status"] == "not_met"


def preview(client, user, code, year, semester="Fall"):
    response = client.get(f"/api/grades/{user.id}/prerequisites/preview",
                          params={"code": code, "year": year, "semester": semester})
    assert response.status_code == 200
    return response.json()


def test_adding_a_future_course_previews_the_shared_rule(db, user, client):
    user.current_school_year, user.current_semester = 2, "Fall"
    db.commit()
    make_course(db, user.id, "CPSC_V 110", year=1, final_grade=80.0)
    shared(db, rule={"all": [{"course": "CPSC 110"}, {"course": "CPSC 121"}]})
    body = preview(client, user, "CPSC_V 221", 3)
    assert body["catalogue"]["subject"] == "CPSC"
    [entry] = body["kinds"]
    assert entry["shared"]["result"]["status"] == "not_met"
    assert [p["status"] for p in entry["shared"]["result"]["parts"]] == ["met", "not_met"]


def test_a_past_term_or_an_unknown_code_previews_nothing(db, user, client):
    user.current_school_year, user.current_semester = 3, "Fall"
    db.commit()
    shared(db)
    assert preview(client, user, "CPSC_V 221", 1) == {"catalogue": None, "kinds": []}
    assert preview(client, user, "ZZZZ 999", 4) == {"catalogue": None, "kinds": []}
