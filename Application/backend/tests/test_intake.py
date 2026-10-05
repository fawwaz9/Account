"""Syllabus intake (Phase 1 item 1): the adapter, the checks, and building a course.

The model is faked everywhere (conftest's _no_llm_network): these pin what is
sent, how answers are read, what is checked, and that nothing becomes a record
without the person's confirmation -- and that a half-built course is never left
behind.
"""
import base64
import datetime
import json

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import CourseModel, GradeModel, SyllabusParseModel
from app.Auth.dependencies import get_current_user
from app.config import settings
from app.Grades.services.course_service import delete_course
from app.Intake.schemas.syllabus import ApplyAssessment, ApplyRequest, SyllabusExtract, SyllabusUpload
from app.Intake.services import llm, syllabus_service
from app.Intake.services.syllabus_service import RateLimited, apply, changes, check, parse, prompt
from tests.conftest import SUITE_SYLLABUS, make_user

PDF = base64.b64encode(b"%PDF-1.4 a syllabus").decode()
D = datetime.date


def upload(**overrides):
    fields = {"filename": "cpsc221.pdf", "media_type": "application/pdf", "content_base64": PDF}
    fields.update(overrides)
    return SyllabusUpload(**fields)


@pytest.fixture
def termed(db, user):
    user.current_school_year, user.current_semester, user.first_year_calendar_year = 2, "Fall", 2025
    db.commit()
    return user


# --- the adapter -----------------------------------------------------------

@pytest.mark.parametrize("provider", ["openai", "gemini", "anthropic"])
def test_each_provider_gets_the_document_and_the_prompt(provider):
    build, _ = llm.PROVIDERS[provider]
    url, headers, body = build("m", "secret-key", "SYSTEM", "PROMPT", b"%PDF", "application/pdf", "s.pdf")
    text = json.dumps(body)
    assert "SYSTEM" in text and "PROMPT" in text
    assert base64.b64encode(b"%PDF").decode() in text
    assert "secret-key" not in url, "a key in the URL ends up in request logs"
    assert "secret-key" in json.dumps(headers)


def test_plain_text_is_sent_as_text():
    _, _, body = llm.openai_request("m", "k", "S", "P", "Week 5: Midterm".encode(), "text/plain", "s.txt")
    assert "Week 5: Midterm" in json.dumps(body)


def test_answers_are_read_from_each_providers_shape():
    assert llm.openai_text({"choices": [{"message": {"content": "{}"}}]}) == "{}"
    assert llm.gemini_text({"candidates": [{"content": {"parts": [{"text": "{"}, {"text": "}"}]}}]}) == "{}"
    assert llm.anthropic_text({"content": [{"type": "text", "text": "{}"}]}) == "{}"


def test_a_fenced_answer_is_still_json_and_anything_else_is_refused():
    assert llm.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(llm.ProviderError):
        llm.parse_json("I could not read it, sorry")
    with pytest.raises(llm.ProviderError):
        llm.parse_json("[1, 2]")


def test_not_configured_means_not_called(monkeypatch, _no_llm_network):
    monkeypatch.setattr(settings, "LLM_API_KEY", None)
    with pytest.raises(llm.NotConfigured):
        llm.extract_document(b"x", "text/plain", "s.txt", "S", "P")
    monkeypatch.setattr(settings, "LLM_API_KEY", "k")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "someone-new")
    with pytest.raises(llm.NotConfigured):
        llm.extract_document(b"x", "text/plain", "s.txt", "S", "P")
    assert _no_llm_network == []


def test_an_unexpected_answer_shape_is_a_provider_error():
    with pytest.raises(llm.ProviderError):
        llm.extract_document(b"x", "text/plain", "s.txt", "S", "P", transport=lambda *a: {"nope": 1})


def test_a_refusal_reports_the_status_and_not_the_body(monkeypatch):
    class Response:
        status_code = 401

        def json(self):
            return {"error": "your request echoed: secret"}

    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: Response())
    with pytest.raises(llm.ProviderError) as caught:
        llm.http_post("https://x", {}, {})
    assert "401" in str(caught.value) and "secret" not in str(caught.value)


# --- reading a syllabus ----------------------------------------------------

def test_a_parse_builds_nothing(db, termed):
    result = parse(db, termed.id, upload())
    assert result.extract.course_code == "CPSC 221"
    assert [a.name for a in result.extract.assessments] == ["Assignments", "Midterm", "Final exam"]
    assert db.query(CourseModel).filter(CourseModel.user_id == termed.id).count() == 0
    assert db.query(GradeModel).count() == 0
    row = db.query(SyllabusParseModel).filter(SyllabusParseModel.id == result.id).one()
    assert row.applied_at is None and row.provider == "openai"


def test_what_is_sent_carries_nothing_about_the_person(db, termed, _no_llm_network):
    parse(db, termed.id, upload())
    [(url, headers, body)] = _no_llm_network
    sent = json.dumps(body)
    assert termed.email not in sent and str(termed.id) not in sent and termed.id.hex not in sent
    assert "2026-09-01" in sent and "2026-12-31" in sent  # the term's dates, to resolve weeks


def test_without_a_known_term_the_model_is_told_not_to_guess_a_year():
    assert "not known" in prompt(None, None)


def test_bad_files_are_refused_before_anything_is_sent(db, termed, _no_llm_network):
    with pytest.raises(ValueError, match="PDF or a plain-text"):
        parse(db, termed.id, upload(media_type="image/png"))
    with pytest.raises(ValueError, match="could not be read"):
        parse(db, termed.id, upload(content_base64="not base64!!"))
    with pytest.raises(ValueError, match="empty"):
        parse(db, termed.id, upload(content_base64=""))
    assert _no_llm_network == []


def test_the_daily_cap(db, termed, monkeypatch):
    monkeypatch.setattr(settings, "LLM_PARSES_PER_DAY", 2)
    parse(db, termed.id, upload())
    parse(db, termed.id, upload())
    with pytest.raises(RateLimited):
        parse(db, termed.id, upload())


def test_another_users_parses_do_not_count_toward_my_cap(db, termed, monkeypatch):
    monkeypatch.setattr(settings, "LLM_PARSES_PER_DAY", 1)
    other = make_user(db, "other@example.com")
    parse(db, other.id, upload())
    parse(db, termed.id, upload())  # not refused


def test_an_unknown_category_is_other_and_unusable_entries_are_dropped(db, termed, monkeypatch, _no_llm_network):
    answer = dict(SUITE_SYLLABUS, assessments=[
        {"name": "Clicker questions", "category": "Clickers", "weight": 5},
        {"weight": 10},  # no name: dropped
        "garbage",
    ])
    monkeypatch.setattr(llm, "_post", lambda *a: {"choices": [{"message": {"content": json.dumps(answer)}}]})
    result = parse(db, termed.id, upload())
    assert [(a.name, a.category.value) for a in result.extract.assessments] == [("Clicker questions", "Other")]


# --- the checks ------------------------------------------------------------

def extract(*assessments, multiple=False):
    return SyllabusExtract(course_code="X 100", course_name="X", multiple_schemes=multiple,
                           assessments=list(assessments))


def item(name, category, weight, due=None, tba=False):
    return {"name": name, "category": category, "weight": weight, "due_date": due, "date_tba": tba}


TERM = (D(2026, 9, 1), D(2026, 12, 31))


def test_weights_must_add_up_bonus_aside():
    ok = extract(item("A", "Assignment", 60, "2026-10-01"), item("F", "Final", 40, tba=True),
                 item("B", "Bonus", 5, "2026-11-01"))
    assert check(ok, *TERM) == []
    short = extract(item("A", "Assignment", 60, "2026-10-01"), item("F", "Final", 30, tba=True))
    assert check(short, *TERM) == ["The weights add up to 90%, not 100%."]


def test_a_weighted_item_needs_a_date_unless_it_is_tba():
    result = check(extract(item("Project", "Project", 50), item("F", "Final", 50, tba=True)), *TERM)
    assert result == ["Project has 50% weight but no date."]


def test_a_date_outside_the_term_is_flagged():
    result = check(extract(item("Midterm", "Midterm", 100, "2027-02-10")), *TERM)
    assert result == ["Midterm is dated 2027-02-10, outside the term."]


def test_more_than_one_scheme_is_said_out_loud():
    result = check(extract(item("F", "Final", 100, tba=True), multiple=True), *TERM)
    assert result == ["The syllabus offers more than one grading scheme; only the first was read."]


# --- building the course ---------------------------------------------------

def confirmed(**overrides):
    fields = {
        "course_code": "CPSC 221", "course_name": "Basic Algorithms and Data Structures",
        "assessments": [
            ApplyAssessment(name="Assignments", category="Assignment", weight=30, count=3),
            ApplyAssessment(name="Midterm", category="Midterm", weight=30, due_date=D(2026, 10, 20)),
            ApplyAssessment(name="Final exam", category="Final", weight=40, date_tba=True),
        ],
    }
    fields.update(overrides)
    return ApplyRequest(**fields)


def test_confirming_builds_the_course_and_its_gradebook(db, termed):
    parsed = parse(db, termed.id, upload())
    result = apply(db, termed.id, parsed.id, confirmed())
    course = db.query(CourseModel).filter(CourseModel.id == result.course_id).one()
    assert (course.code, course.year, course.semester) == ("CPSC 221", 2, "Fall")
    assert {k: v for k, v in course.category_weights.items() if v} == {
        "Assignment": 30.0, "Midterm": 30.0, "Final": 40.0,
    }
    grades = {g.name: g for g in db.query(GradeModel).filter(GradeModel.course_id == course.id)}
    assert sorted(grades) == ["Assignments 1", "Assignments 2", "Assignments 3", "Final exam", "Midterm"]
    assert grades["Midterm"].due_date == D(2026, 10, 20) and grades["Midterm"].schedule_as == "event"
    assert grades["Assignments 1"].schedule_as == "task"
    assert all(g.score is None for g in grades.values())
    assert result.grades_created == 5


def test_the_section_confirmed_is_the_courses(db, termed):
    parsed = parse(db, termed.id, upload())
    result = apply(db, termed.id, parsed.id, confirmed(section=" 101 "))
    course = db.query(CourseModel).filter(CourseModel.id == result.course_id).one()
    assert course.section == "101"


def test_a_section_filled_in_is_not_counted_as_a_correction(db, termed):
    """Many syllabi serve every section and name none; filling it in is
    adding what the document never had, not fixing what the model read."""
    parsed = parse(db, termed.id, upload())
    result = apply(db, termed.id, parsed.id, confirmed(section="101"))
    assert (result.fields_total, result.fields_changed) == (3 * 6 + 2, 0)


def test_the_prompt_asks_for_the_section():
    assert '"section"' in prompt(None, None)


def test_no_change_is_measured(db, termed):
    parsed = parse(db, termed.id, upload())
    untouched = apply(db, termed.id, parsed.id, confirmed())
    assert (untouched.fields_total, untouched.fields_changed) == (3 * 6 + 2, 0)

    parsed = parse(db, termed.id, upload())
    edited = confirmed(course_code="CPSC 221A", assessments=[
        ApplyAssessment(name="Assignments", category="Assignment", weight=25, count=3),
        ApplyAssessment(name="Midterm", category="Midterm", weight=35, due_date=D(2026, 10, 21)),
        ApplyAssessment(name="Final exam", category="Final", weight=40, date_tba=True),
    ])
    result = apply(db, termed.id, parsed.id, edited)
    assert result.fields_changed == 4  # code, two weights, one date
    row = db.query(SyllabusParseModel).filter(SyllabusParseModel.id == parsed.id).one()
    assert (row.fields_total, row.fields_changed, row.course_id) == (20, 4, result.course_id)


def test_adding_or_removing_a_row_counts_all_its_fields():
    base = SyllabusExtract.model_validate(SUITE_SYLLABUS)
    fewer = confirmed(assessments=[
        ApplyAssessment(name="Assignments", category="Assignment", weight=60, count=3),
        ApplyAssessment(name="Midterm", category="Midterm", weight=40, due_date=D(2026, 10, 20)),
    ])
    assert changes(base, fewer) == (20, 6 + 2)  # the dropped final's six, and two weights


def test_weights_that_do_not_add_up_build_nothing(db, termed):
    parsed = parse(db, termed.id, upload())
    with pytest.raises(ValueError, match="add up to 90%"):
        apply(db, termed.id, parsed.id, confirmed(assessments=[
            ApplyAssessment(name="A", category="Assignment", weight=50),
            ApplyAssessment(name="F", category="Final", weight=40),
        ]))
    assert db.query(CourseModel).filter(CourseModel.user_id == termed.id).count() == 0


def test_a_parse_builds_one_course_only(db, termed):
    parsed = parse(db, termed.id, upload())
    apply(db, termed.id, parsed.id, confirmed())
    with pytest.raises(ValueError, match="already built"):
        apply(db, termed.id, parsed.id, confirmed(course_code="CPSC 999"))


def test_an_existing_course_code_is_refused(db, termed):
    first = parse(db, termed.id, upload())
    apply(db, termed.id, first.id, confirmed())
    second = parse(db, termed.id, upload())
    with pytest.raises(ValueError, match="already have a course CPSC 221"):
        apply(db, termed.id, second.id, confirmed())


def test_without_a_term_the_person_has_to_choose_one(db, user):
    parsed = parse(db, user.id, upload())
    with pytest.raises(ValueError, match="current term"):
        apply(db, user.id, parsed.id, confirmed())
    result = apply(db, user.id, parsed.id, confirmed(year=1, semester="Winter"))
    assert db.query(CourseModel).filter(CourseModel.id == result.course_id).one().semester == "Winter"


def test_a_failed_gradebook_leaves_no_course_behind(db, termed, monkeypatch):
    parsed = parse(db, termed.id, upload())

    def broken(*a, **k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(syllabus_service, "add_grades_bulk", broken)
    with pytest.raises(RuntimeError):
        apply(db, termed.id, parsed.id, confirmed())
    assert db.query(CourseModel).filter(CourseModel.user_id == termed.id).count() == 0
    row = db.query(SyllabusParseModel).filter(SyllabusParseModel.id == parsed.id).one()
    assert row.applied_at is None


def test_someone_elses_parse_builds_nothing_for_me(db, termed):
    other = make_user(db, "other@example.com")
    theirs = parse(db, other.id, upload())
    assert apply(db, termed.id, theirs.id, confirmed()) is None
    assert db.query(CourseModel).count() == 0


def test_deleting_the_course_keeps_the_parse_and_its_measure(db, termed):
    parsed = parse(db, termed.id, upload())
    result = apply(db, termed.id, parsed.id, confirmed())
    delete_course(db, termed.id, result.course_id)
    row = db.query(SyllabusParseModel).filter(SyllabusParseModel.id == parsed.id).one()
    assert row.course_id is None and row.fields_total == 20


# --- the routes ------------------------------------------------------------

@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_routes(db, user, client, monkeypatch):
    base = f"/api/intake/{user.id}"
    body = {"filename": "s.pdf", "media_type": "application/pdf", "content_base64": PDF}
    assert client.get(f"{base}/status").json() == {"available": True}
    parsed = client.post(f"{base}/syllabus", json=body).json()
    assert parsed["extract"]["course_code"] == "CPSC 221"
    applied = client.post(f"{base}/syllabus/{parsed['id']}/apply", json={
        "course_code": "CPSC 221", "course_name": "Algorithms", "year": 2, "semester": "Fall",
        "assessments": [{"name": "Final", "category": "Final", "weight": 100}],
    })
    assert applied.status_code == 200 and applied.json()["grades_created"] == 1

    monkeypatch.setattr(llm, "_post", lambda *a: (_ for _ in ()).throw(llm.ProviderError("timed out")))
    assert client.post(f"{base}/syllabus", json=body).status_code == 502
    monkeypatch.setattr(settings, "LLM_PARSES_PER_DAY", 1)
    assert client.post(f"{base}/syllabus", json=body).status_code == 429
    monkeypatch.setattr(settings, "LLM_API_KEY", None)
    assert client.get(f"{base}/status").json() == {"available": False}
    assert client.post(f"{base}/syllabus", json=body).status_code == 503
