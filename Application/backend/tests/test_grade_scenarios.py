"""Grade scenarios (Phase 4 item 10, §13.6).

The invariant first: a scenario is the grade engine, not a second one. With
nothing set, it is `project_course` at the assumed score; with scores set, it is
`project_course` with those overrides; at 100 and 0 it is the band. Then the
boundaries: only this course's unmarked work can be set, scores outside 0-100 are
refused rather than computed, another user's course is a 404, and nothing is
written.
"""
import random
import uuid

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import CourseModel, GradeModel
from app.Auth.dependencies import get_current_user
from app.Grades.schemas.scenario import GradeScenarioIn
from app.Grades.services.grade_service import calculate_grade_band, get_user_course, project_course
from app.Grades.services.scenario_service import scenario
from conftest import make_course, make_user


def grade(db, course, category, got=None, out_of=100.0, excluded=False, name=None):
    row = GradeModel(id=uuid.uuid4(), course_id=course.id, name=name or f"{category} {uuid.uuid4().hex[:4]}",
                     category=category, score=got, max_score=out_of, weight=0.0, excluded=excluded)
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def course(db, user):
    """Assignments 30, Midterm 30, Final 40: two marked, three unmarked, two dropped."""
    row = make_course(db, user.id, "CPSC 221",
                      category_weights={"Assignment": 30.0, "Midterm": 30.0, "Final": 40.0})
    grade(db, row, "Assignment", 80, name="A1")
    grade(db, row, "Assignment", None, name="A2")
    grade(db, row, "Assignment", 20, excluded=True, name="A0 dropped")
    grade(db, row, "Assignment", None, excluded=True, name="A4 dropped, unmarked")
    grade(db, row, "Midterm", 65, name="Midterm")
    grade(db, row, "Final", None, name="Final exam")
    grade(db, row, "Assignment", None, out_of=50.0, name="A3")
    return row


def fresh(db, user, course):
    db.expire_all()
    return get_user_course(db, user.id, course.id)


def by_name(result):
    return {item.name: item for item in result.items}


# ---------------------------------------------------------------- the engine --

@pytest.mark.parametrize("assume", [0, 37.5, 72, 100])
def test_nothing_set_is_project_course_at_the_assumption(db, user, course, assume):
    result = scenario(db, user.id, course.id, GradeScenarioIn(assume=assume))

    assert result.projected == project_course(fresh(db, user, course), assume / 100)


def test_scores_set_are_project_course_with_overrides(db, user, course):
    items = {g.name: g for g in fresh(db, user, course).grades}
    scores = {items["Final exam"].id: 90.0, items["A2"].id: 0.0}

    result = scenario(db, user.id, course.id, GradeScenarioIn(assume=70, scores=scores))

    expected = project_course(fresh(db, user, course), 0.7, {k: v / 100 for k, v in scores.items()})
    assert result.projected == expected
    named = by_name(result)
    assert (named["Final exam"].percent, named["Final exam"].set) == (90.0, True)
    assert (named["A3"].percent, named["A3"].set) == (70.0, False)


def test_the_band_is_the_grade_band(db, user, course):
    result = scenario(db, user.id, course.id, GradeScenarioIn(assume=50))
    band = calculate_grade_band(db, user.id, course.id)

    assert (result.best, result.worst, result.current) == (band["best"], band["worst"], band["current"])


def test_many_generated_courses_agree_with_the_engine(db, user):
    """Not a hand-picked example: random weights, marks and overrides, 30 courses."""
    rng = random.Random(4)
    for n in range(30):
        weights = {"Assignment": rng.choice([10.0, 25.0, 40.0]), "Midterm": rng.choice([0.0, 20.0, 30.0]),
                   "Final": rng.choice([30.0, 40.0, 50.0])}
        row = make_course(db, user.id, f"GEN {n}", category_weights=weights)
        for category in weights:
            for _ in range(rng.randint(0, 3)):
                marked = rng.random() < 0.5
                grade(db, row, category, rng.uniform(0, 100) if marked else None,
                      excluded=rng.random() < 0.1)
        loaded = fresh(db, user, row)
        unmarked = [g.id for g in loaded.grades if g.score is None and not g.excluded]
        scores = {gid: round(rng.uniform(0, 100), 1) for gid in unmarked if rng.random() < 0.5}
        assume = round(rng.uniform(0, 100), 1)

        result = scenario(db, user.id, row.id, GradeScenarioIn(assume=assume, scores=scores))

        assert result.projected == project_course(
            fresh(db, user, row), assume / 100, {k: v / 100 for k, v in scores.items()}), row.code


# -------------------------------------------------------------- what it lists --

def test_lists_only_unmarked_counted_work_by_due_date(db, user, course):
    result = scenario(db, user.id, course.id, GradeScenarioIn(assume=60))

    assert sorted(by_name(result)) == ["A2", "A3", "Final exam"]


def test_an_empty_weighted_category_counts_at_the_assumption_and_is_said(db, user):
    row = make_course(db, user.id, "MATH 200", category_weights={"Assignment": 50.0, "Final": 50.0})
    grade(db, row, "Assignment", 80)

    result = scenario(db, user.id, row.id, GradeScenarioIn(assume=60))

    assert result.empty_categories == ["Final"]
    assert result.projected == 70.0
    assert any("Final" in line for line in result.assumptions)


# ---------------------------------------------------------------- boundaries --

def test_a_marked_assessment_cannot_be_set(db, user, course):
    marked = next(g for g in fresh(db, user, course).grades if g.name == "A1")

    with pytest.raises(ValueError):
        scenario(db, user.id, course.id, GradeScenarioIn(assume=50, scores={marked.id: 10.0}))


def test_a_dropped_assessment_cannot_be_set(db, user, course):
    dropped = next(g for g in fresh(db, user, course).grades if g.name == "A4 dropped, unmarked")

    with pytest.raises(ValueError):
        scenario(db, user.id, course.id, GradeScenarioIn(assume=50, scores={dropped.id: 10.0}))


def test_another_course_s_assessment_cannot_be_set(db, user, course):
    other = make_course(db, user.id, "OTHER 100")
    theirs = grade(db, other, "Assignment", None)

    with pytest.raises(ValueError):
        scenario(db, user.id, course.id, GradeScenarioIn(assume=50, scores={theirs.id: 10.0}))


def test_another_user_s_course_is_not_found(db, user, course):
    stranger = make_user(db, "stranger@example.com")

    assert scenario(db, stranger.id, course.id, GradeScenarioIn(assume=50)) is None


@pytest.mark.parametrize("body", [
    {"assume": 101},
    {"assume": -1},
    {"assume": 50, "scores": {str(uuid.uuid4()): 100.01}},
    {"assume": 50, "scores": {str(uuid.uuid4()): -0.5}},
])
def test_absurd_inputs_are_refused_not_computed(body):
    with pytest.raises(ValueError):
        GradeScenarioIn(**body)


def test_nothing_is_written(db, user, course):
    def snapshot():
        db.expire_all()
        row = db.query(CourseModel).filter(CourseModel.id == course.id).one()
        return row.average, sorted((g.name, g.score) for g in row.grades)

    before = snapshot()
    unmarked = next(g for g in fresh(db, user, course).grades if g.name == "Final exam")
    scenario(db, user.id, course.id, GradeScenarioIn(assume=100, scores={unmarked.id: 100.0}))

    assert snapshot() == before


# --------------------------------------------------------------------- route --

@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_route(db, user, course, client):
    final = next(g for g in fresh(db, user, course).grades if g.name == "Final exam")
    url = f"/api/grades/{user.id}/courses/{course.id}/scenario"

    answer = client.post(url, json={"assume": 70, "scores": {str(final.id): 85}})
    assert answer.status_code == 200
    body = answer.json()
    assert body["projected"] == project_course(fresh(db, user, course), 0.7, {final.id: 0.85})
    assert body["letter"]

    marked = next(g for g in fresh(db, user, course).grades if g.name == "A1")
    assert client.post(url, json={"assume": 70, "scores": {str(marked.id): 85}}).status_code == 422
    assert client.post(url, json={"assume": 170}).status_code == 422
    missing = f"/api/grades/{user.id}/courses/{uuid.uuid4()}/scenario"
    assert client.post(missing, json={"assume": 70}).status_code == 404
