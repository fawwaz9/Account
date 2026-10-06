"""The syllabus reader picks up prerequisites (Phase 2 item 5, D14).

"Done when": a syllabus that lists prerequisites produces proposals you
confirmed, and nothing you didn't. The syllabus's own sentence stays with you;
only the reviewed tree is ever shared (D6).
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.main
from app._database.db import get_db
from app._database.models import (
    CataloguePrerequisiteModel, CourseModel, PrerequisiteProposalModel,
)
from app.Auth.dependencies import get_current_user
from app.Intake.schemas.syllabus import AddRequest, ApplyRequest, ConfirmedRule, SyllabusUpload
from app.Intake.services import llm
from app.Intake.services.syllabus_service import add_to_course, apply, parse, preview_add, prompt
from conftest import SUITE_SYLLABUS, make_course

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import catalogue_review as review  # noqa: E402

PDF = "JVBERi0xLjQgdGVzdA=="
SENTENCE = "Pre-reqs: CPSC 210 and one of MATH 200, MATH 217. Third-year standing."
STATED = {
    "rule": {"all": [{"course": "CPSC 210"}, {"any": [{"course": "MATH 200"}, {"course": "MATH 217"}]}]},
    "note": "Third-year standing", "sentence": SENTENCE,
}


@pytest.fixture
def termed(db, user):
    user.current_school_year, user.current_semester, user.first_year_calendar_year = 3, "Fall", 2024
    db.commit()
    return user


def answer_with(monkeypatch, **fields):
    body = dict(SUITE_SYLLABUS, **fields)
    monkeypatch.setattr(llm, "_post", lambda *a: {"choices": [{"message": {"content": json.dumps(body)}}]})


def upload():
    return SyllabusUpload(filename="cpsc221.pdf", media_type="application/pdf", content_base64=PDF)


def confirmed(**overrides):
    fields = {
        "course_code": "CPSC_V 221", "course_name": "Algorithms", "credits": 4.0,
        "assessments": [{"name": "Final", "category": "Final", "weight": 100, "date_tba": True}],
    }
    fields.update(overrides)
    return ApplyRequest(**fields)


def test_the_prompt_asks_for_prerequisites_and_their_own_words():
    text = prompt(None, None)
    assert '"prerequisites"' in text and '"corequisites"' in text and '"sentence"' in text
    assert '{"course": "CPSC 210"}' in text and "min_grade" in text


def test_a_stated_rule_is_read_and_shown_in_the_typed_form(db, termed, monkeypatch):
    answer_with(monkeypatch, prerequisites=STATED)
    result = parse(db, termed.id, upload())
    found = result.extract.prerequisites
    assert found.text == "CPSC 210 and (one of MATH 200, MATH 217)"
    assert found.note == "Third-year standing" and found.sentence == SENTENCE
    assert result.extract.corequisites is None


@pytest.mark.parametrize("given", [None, "CPSC 210", [], {}, {"rule": None, "note": None, "sentence": ""}])
def test_nothing_usable_is_no_rule(db, termed, monkeypatch, given):
    answer_with(monkeypatch, prerequisites=given)
    assert parse(db, termed.id, upload()).extract.prerequisites is None


def test_an_unreadable_tree_keeps_the_sentence_and_says_so(db, termed, monkeypatch):
    answer_with(monkeypatch, prerequisites={"rule": {"course": "some calculus"}, "sentence": "Some calculus."})
    result = parse(db, termed.id, upload())
    found = result.extract.prerequisites
    assert found.rule is None and found.text == "" and found.sentence == "Some calculus."
    assert any("couldn't be read as a rule" in w for w in result.warnings)


def test_confirming_files_your_rule_with_the_syllabus_sentence_kept_with_you(db, termed, monkeypatch):
    answer_with(monkeypatch, prerequisites=STATED)
    parsed = parse(db, termed.id, upload())
    result = apply(db, termed.id, parsed.id, confirmed(
        prerequisites={"text": "CPSC 210 and one of MATH 200, MATH 217", "note": "Third-year standing"}))
    [row] = db.query(PrerequisiteProposalModel).filter_by(course_id=result.course_id).all()
    assert (row.kind, row.source, row.status, row.session) == ("prerequisite", "syllabus", "pending", "2026W")
    assert row.source_text == SENTENCE and row.note == "Third-year standing"


def test_what_you_leave_out_is_not_filed(db, termed, monkeypatch):
    answer_with(monkeypatch, prerequisites=STATED, corequisites={"rule": {"course": "CPSC 213"}, "sentence": "Co: 213"})
    parsed = parse(db, termed.id, upload())
    result = apply(db, termed.id, parsed.id, confirmed())
    assert db.query(PrerequisiteProposalModel).filter_by(course_id=result.course_id).count() == 0


def test_what_you_edit_is_what_is_filed(db, termed, monkeypatch):
    answer_with(monkeypatch, prerequisites=STATED)
    parsed = parse(db, termed.id, upload())
    result = apply(db, termed.id, parsed.id, confirmed(prerequisites={"text": "CPSC 213"}))
    [row] = db.query(PrerequisiteProposalModel).filter_by(course_id=result.course_id).all()
    assert row.rule == {"course": "CPSC 213"}


@pytest.mark.parametrize("text", ["", "permission of the instructor", "CPSC"])
def test_an_unreadable_confirmation_is_refused_before_anything_is_built(text):
    with pytest.raises(ValidationError):
        ConfirmedRule(text=text)


def test_an_unreadable_confirmation_through_the_api_builds_nothing(db, termed, monkeypatch):
    answer_with(monkeypatch, prerequisites=STATED)
    parsed = parse(db, termed.id, upload())
    app.main.app.dependency_overrides[get_current_user] = lambda: termed
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        body = confirmed().model_dump(mode="json")
        body["prerequisites"] = {"text": "permission of the instructor"}
        response = TestClient(app.main.app).post(f"/api/intake/{termed.id}/syllabus/{parsed.id}/apply", json=body)
    finally:
        app.main.app.dependency_overrides.clear()
    assert response.status_code == 422
    assert db.query(CourseModel).filter_by(user_id=termed.id).count() == 0


def test_adding_to_a_course_offers_the_rule_beside_yours_and_files_only_if_confirmed(db, termed, monkeypatch):
    answer_with(monkeypatch, prerequisites=STATED)
    course = make_course(db, termed.id, "CPSC_V 221", year=3)
    first = parse(db, termed.id, upload())
    preview = preview_add(db, termed.id, first.id, course.id)
    assert preview.prerequisites.text.startswith("CPSC 210") and preview.own_prerequisites is None

    add_to_course(db, termed.id, first.id, course.id, AddRequest(rows=[]))
    assert db.query(PrerequisiteProposalModel).filter_by(course_id=course.id).count() == 0

    second = parse(db, termed.id, upload())
    add_to_course(db, termed.id, second.id, course.id,
                  AddRequest(rows=[], prerequisites={"text": "CPSC 210 and one of MATH 200, MATH 217"}))
    row = db.query(PrerequisiteProposalModel).filter_by(course_id=course.id).one()
    assert row.source == "syllabus" and row.source_text == SENTENCE
    third = parse(db, termed.id, upload())
    assert preview_add(db, termed.id, third.id, course.id).own_prerequisites == "CPSC 210 and (one of MATH 200, MATH 217)"


def test_the_syllabus_wording_never_reaches_the_catalogue(db, termed, monkeypatch):
    """End to end: read, confirm, approve. The shared row is the tree alone."""
    answer_with(monkeypatch, prerequisites=STATED)
    parsed = parse(db, termed.id, upload())
    apply(db, termed.id, parsed.id, confirmed(
        prerequisites={"text": "CPSC 210 and one of MATH 200, MATH 217", "note": "Third-year standing"}))
    [group] = review.pending_groups(db)
    review.approve(db, group.id)
    shared = db.query(CataloguePrerequisiteModel).one()
    assert shared.source_text is None and shared.note is None
    assert SENTENCE not in json.dumps(shared.rule)
