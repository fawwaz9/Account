"""A syllabus adding to a course you already have -- add-only (Phase 1 D27).

The rule: it may add the assessments a course lacks, and nothing else. No mark,
weight, date or name you entered changes. A match that isn't clear counts as
existing, because a duplicate is worse than a row left for you to add; and an
existing row matches at most once.
"""
import base64
import datetime
import uuid

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import CourseModel, GradeModel, SyllabusParseModel
from app.Auth.dependencies import get_current_user
from app.Intake.schemas.syllabus import AddRequest, AddRow, SyllabusUpload
from app.Intake.services.syllabus_service import _words, add_to_course, match_rows, parse, preview_add
from conftest import make_course, make_user

PDF = base64.b64encode(b"%PDF-1.4 a syllabus").decode()
D = datetime.date


@pytest.fixture
def termed(db, user):
    user.current_school_year, user.current_semester, user.first_year_calendar_year = 2, "Fall", 2025
    db.commit()
    return user


class G:
    def __init__(self, name, category):
        self.name, self.category = name, category


# --- matching --------------------------------------------------------------

@pytest.mark.parametrize("a, b", [
    ("Assignments 1", "assignment 1"),
    ("Quizzes", "Quiz"),
    ("Midterm-Exam", "midterm exam"),
    ("Case Studies", "case study"),
])
def test_names_compare_without_case_punctuation_or_plurals(a, b):
    assert _words(a) == _words(b)


def test_numbers_keep_items_apart():
    assert match_rows([G("Assignment 1", "Assignment")], [("Assignment 10", "Assignment")]) == [None]


def test_the_category_must_agree():
    assert match_rows([G("Project", "Project")], [("Project", "Assignment")]) == [None]


def test_an_unclear_match_counts_as_existing_but_only_once():
    existing = [G("Midterm", "Midterm")]
    assert match_rows(existing, [("Midterm 1", "Midterm"), ("Midterm 2", "Midterm")]) == ["Midterm", None]


def test_an_exact_match_is_taken_before_a_loose_one():
    """The course has "Midterm"; the syllabus lists "Midterm 1" then "Midterm".
    Taken in order, the loose "Midterm 1" would claim it and "Midterm" would be
    added again -- a duplicate. Exact first, "Midterm" keeps its match and
    "Midterm 1" is the new row."""
    existing = [G("Midterm", "Midterm")]
    assert match_rows(existing, [("Midterm 1", "Midterm"), ("Midterm", "Midterm")]) == [None, "Midterm"]


# --- the preview -----------------------------------------------------------

def course_with(db, user, *grades, weights=None, section=None):
    course = make_course(db, user.id, "CPSC 221", section=section,
                         category_weights=weights or {"Assignment": 30.0, "Midterm": 30.0, "Final": 40.0})
    for name, category, score in grades:
        db.add(GradeModel(id=uuid.uuid4(), course_id=course.id, name=name, category=category,
                          score=score, max_score=100.0, weight=0.0, due_date=D(2026, 9, 30)))
    db.commit()
    return course


def read(db, user):
    return parse(db, user.id, SyllabusUpload(filename="s.pdf", media_type="application/pdf", content_base64=PDF))


def test_the_preview_marks_what_the_course_has(db, termed):
    # The suite's syllabus: Assignments x3 (30), Midterm (30, Oct 20), Final exam (40, TBA).
    course = course_with(db, termed, ("Assignment 1", "Assignment", 85.0), ("Midterm", "Midterm", None))
    preview = preview_add(db, termed.id, read(db, termed).id, course.id)
    assert [(r.name, r.exists, r.matched) for r in preview.rows] == [
        ("Assignments 1", True, "Assignment 1"),
        ("Assignments 2", False, None),
        ("Assignments 3", False, None),
        ("Midterm", True, "Midterm"),
        ("Final exam", False, None),
    ]
    assert preview.weight_notes == [] and preview.unweighted == []


def test_differing_weights_are_reported_and_unweighted_categories_named(db, termed):
    course = course_with(db, termed, weights={"Assignment": 25.0, "Midterm": 35.0})
    preview = preview_add(db, termed.id, read(db, termed).id, course.id)
    assert {(n.category.value, n.syllabus, n.course) for n in preview.weight_notes} == {
        ("Assignment", 30.0, 25.0), ("Midterm", 30.0, 35.0), ("Final", 40.0, 0.0),
    }
    assert [c.value for c in preview.unweighted] == ["Final"]


def test_the_section_is_offered_only_when_the_course_has_none(db, termed, _no_llm_network, monkeypatch):
    import json
    from tests.conftest import SUITE_SYLLABUS
    from app.Intake.services import llm
    monkeypatch.setattr(llm, "_post", lambda u, h, b: {"choices": [{"message": {
        "content": json.dumps(dict(SUITE_SYLLABUS, section="101"))}}]})
    empty = course_with(db, termed)
    assert preview_add(db, termed.id, read(db, termed).id, empty.id).section_offer == "101"
    other = make_course(db, termed.id, "CPSC 999", section="102")
    assert preview_add(db, termed.id, read(db, termed).id, other.id).section_offer is None


# --- adding ----------------------------------------------------------------

def snapshot(db, course_id):
    db.expire_all()
    course = db.query(CourseModel).filter(CourseModel.id == course_id).one()
    grades = sorted((g.name, g.category, g.score, g.max_score, g.due_date, g.excluded)
                    for g in db.query(GradeModel).filter(GradeModel.course_id == course_id))
    return course.category_weights, course.section, grades


def test_adding_writes_only_new_rows_and_changes_nothing_else(db, termed):
    course = course_with(db, termed, ("Assignment 1", "Assignment", 85.0), ("Midterm", "Midterm", 70.0))
    weights_before, section_before, grades_before = snapshot(db, course.id)
    parsed = read(db, termed)
    result = add_to_course(db, termed.id, parsed.id, course.id, AddRequest(rows=[
        AddRow(name="Assignments 2", category="Assignment"),
        AddRow(name="Final exam", category="Final"),
    ]))
    assert (result.added, result.skipped) == (2, 0)
    weights_after, section_after, grades_after = snapshot(db, course.id)
    assert (weights_after, section_after) == (weights_before, section_before)
    assert set(grades_before) <= set(grades_after)  # every old row, untouched
    added = sorted(set(grades_after) - set(grades_before))
    assert [(name, category, score) for name, category, score, *_ in added] == [
        ("Assignments 2", "Assignment", None), ("Final exam", "Final", None)]
    final = db.query(GradeModel).filter(GradeModel.name == "Final exam").one()
    assert final.schedule_as == "event"
    row = db.query(SyllabusParseModel).filter(SyllabusParseModel.id == parsed.id).one()
    assert row.course_id == course.id and row.applied_at is not None


def test_a_row_the_course_already_has_is_skipped_even_if_sent(db, termed):
    """Sent anyway -- an edited client, or a row added since the preview."""
    course = course_with(db, termed, ("Midterm", "Midterm", 70.0))
    result = add_to_course(db, termed.id, read(db, termed).id, course.id, AddRequest(rows=[
        AddRow(name="Midterm", category="Midterm"),
        AddRow(name="Final exam", category="Final"),
        AddRow(name="final exam", category="Final"),  # the same row twice
    ]))
    assert (result.added, result.skipped) == (1, 2)
    assert db.query(GradeModel).filter(GradeModel.course_id == course.id, GradeModel.category == "Midterm").count() == 1


def test_the_section_is_filled_only_when_asked_and_empty(db, termed, monkeypatch):
    import json
    from tests.conftest import SUITE_SYLLABUS
    from app.Intake.services import llm
    monkeypatch.setattr(llm, "_post", lambda u, h, b: {"choices": [{"message": {
        "content": json.dumps(dict(SUITE_SYLLABUS, section="101"))}}]})
    empty = course_with(db, termed)
    assert add_to_course(db, termed.id, read(db, termed).id, empty.id,
                         AddRequest(rows=[], set_section=True)).section_set is True
    assert snapshot(db, empty.id)[1] == "101"
    kept = make_course(db, termed.id, "CPSC 999", section="102")
    assert add_to_course(db, termed.id, read(db, termed).id, kept.id,
                         AddRequest(rows=[], set_section=True)).section_set is False
    assert snapshot(db, kept.id)[1] == "102"


def test_a_syllabus_is_used_once(db, termed):
    course = course_with(db, termed)
    parsed = read(db, termed)
    add_to_course(db, termed.id, parsed.id, course.id, AddRequest(rows=[]))
    with pytest.raises(ValueError, match="already been used"):
        add_to_course(db, termed.id, parsed.id, course.id, AddRequest(rows=[]))


def test_someone_elses_parse_or_course_finds_nothing(db, termed):
    course = course_with(db, termed)
    parsed = read(db, termed)
    other = make_user(db, "other@example.com")
    theirs = make_course(db, other.id, "MATH 100")
    assert preview_add(db, other.id, parsed.id, course.id) is None
    assert preview_add(db, termed.id, parsed.id, theirs.id) is None
    assert add_to_course(db, termed.id, parsed.id, theirs.id,
                         AddRequest(rows=[AddRow(name="X", category="Final")])) is None
    assert db.query(GradeModel).filter(GradeModel.course_id == theirs.id).count() == 0


@pytest.fixture
def client(db, termed):
    app.main.app.dependency_overrides[get_current_user] = lambda: termed
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_routes(db, termed, client):
    course = course_with(db, termed, ("Midterm", "Midterm", 70.0))
    parsed = read(db, termed)
    url = f"/api/intake/{termed.id}/syllabus/{parsed.id}/add-to/{course.id}"
    preview = client.get(url).json()
    assert [r["exists"] for r in preview["rows"]] == [False, False, False, True, False]
    done = client.post(url, json={"rows": [{"name": "Final exam", "category": "Final"}]})
    assert done.status_code == 200 and done.json()["added"] == 1
    assert client.post(url, json={"rows": []}).status_code == 400
    assert client.get(f"/api/intake/{termed.id}/syllabus/{parsed.id}/add-to/{uuid.uuid4()}").status_code == 404
