"""Alternative grading schemes (Phase 1 item 4).

The invariant first: a scheme with the course's own weights and no rules gives
exactly the course's average, checked against calculate_current_average over
many generated courses -- bonus, exclusions, partial marking, weights past 100.
A scheme may only ever differ for a reason it shows.
"""
import random
import uuid

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import GradeModel, GradingSchemeModel
from app.Auth.dependencies import get_current_user
from app.Grades.schemas.scheme import SchemeComponent, SchemeWrite
from app.Grades.services.course_service import delete_course
from app.Grades.services.grade_service import calculate_current_average, get_user_course
from app.Grades.services.scheme_service import (
    category_average,
    compare,
    create_scheme,
    delete_scheme,
    own_components,
    project,
    update_scheme,
)
from tests.conftest import make_course, make_user


def mark(db, course, category, got, out_of=100.0, excluded=False, name=None):
    db.add(GradeModel(id=uuid.uuid4(), course_id=course.id, name=name or f"{category} {got}",
                      category=category, score=got, max_score=out_of, weight=0.0, excluded=excluded))
    db.commit()


def fresh(db, user, course):
    return get_user_course(db, user.id, course.id)


def scheme(*components, label="B"):
    return SchemeWrite(label=label, components=[SchemeComponent(**c) for c in components])


# --- the invariant ---------------------------------------------------------

def test_the_course_own_weights_give_exactly_the_course_average(db, user):
    rng = random.Random(20261005)
    categories = ["Assignment", "Lab", "Quiz", "Midterm", "Project", "Final", "Bonus"]
    nonzero = 0
    for n in range(40):
        chosen = rng.sample(categories, rng.randint(1, 5))
        weights = {c: float(rng.choice([5, 10, 15, 20, 25, 30, 40])) for c in chosen}
        course = make_course(db, user.id, f"GEN {n:03d}", category_weights=weights)
        for _ in range(rng.randint(0, 8)):
            category = rng.choice(chosen + ["Other"])
            out_of = float(rng.choice([10, 20, 50, 100]))
            mark(db, course, category, round(rng.uniform(0, out_of * 1.1), 1), out_of,
                 excluded=rng.random() < 0.15)
        course = fresh(db, user, course)
        expected = calculate_current_average(course)
        assert project(course, own_components(course), "own").average == expected, (n, weights)
        assert compare(db, user.id, course.id).current.average == expected
        nonzero += expected > 0
    assert nonzero >= 25, "most generated courses must have marks, or this proves nothing"


def test_category_average_agrees_with_the_courses_when_nothing_is_dropped(db, user):
    from app.Grades.services.grade_service import calculate_grade_category_average

    course = make_course(db, user.id, "CPSC 100", category_weights={"Quiz": 100.0})
    for got, out_of in ((8, 10), (45, 100), (17, 20)):
        mark(db, course, "Quiz", got, out_of)
    course = fresh(db, user, course)
    assert category_average(course, "Quiz")[0] == calculate_grade_category_average(course, "Quiz")


# --- the rules -------------------------------------------------------------

def test_dropping_the_lowest_marks(db, user):
    course = make_course(db, user.id, "CPSC 110", category_weights={"Quiz": 100.0})
    for got in (50, 70, 90):
        mark(db, course, "Quiz", got)
    course = fresh(db, user, course)
    assert category_average(course, "Quiz", drop_lowest=1) == (80.0, 1)
    # Never every mark: two marks and "drop five" drops one.
    assert category_average(course, "Quiz", drop_lowest=5) == (90.0, 2)


def test_the_lowest_is_by_percentage_not_points(db, user):
    course = make_course(db, user.id, "CPSC 111", category_weights={"Quiz": 100.0})
    mark(db, course, "Quiz", 8, 10)    # 80%
    mark(db, course, "Quiz", 45, 100)  # 45%: the one to drop, though more points
    course = fresh(db, user, course)
    assert category_average(course, "Quiz", drop_lowest=1) == (80.0, 1)


def test_a_dropped_mark_already_excluded_is_not_dropped_twice(db, user):
    course = make_course(db, user.id, "CPSC 112", category_weights={"Quiz": 100.0})
    mark(db, course, "Quiz", 10, excluded=True)
    for got in (60, 80, 100):
        mark(db, course, "Quiz", got)
    course = fresh(db, user, course)
    assert category_average(course, "Quiz", drop_lowest=1) == (90.0, 1)


def test_the_final_replaces_the_midterm_when_higher(db, user):
    course = make_course(db, user.id, "CPSC 210", category_weights={"Midterm": 40.0, "Final": 60.0})
    mark(db, course, "Midterm", 60)
    mark(db, course, "Final", 80)
    course = fresh(db, user, course)
    result = project(course, [
        SchemeComponent(category="Midterm", weight=40, replace_with="Final"),
        SchemeComponent(category="Final", weight=60),
    ], "replace")
    midterm = result.lines[0]
    assert (midterm.average, midterm.replaced_by.value) == (80.0, "Final")
    assert result.average == 80.0  # (80 x 40 + 80 x 60) / 100


def test_a_lower_or_missing_final_replaces_nothing(db, user):
    course = make_course(db, user.id, "CPSC 213", category_weights={"Midterm": 40.0, "Final": 60.0})
    mark(db, course, "Midterm", 70)
    course = fresh(db, user, course)
    components = [SchemeComponent(category="Midterm", weight=40, replace_with="Final"),
                  SchemeComponent(category="Final", weight=60)]
    assert project(course, components, "x").lines[0].replaced_by is None  # no final yet
    mark(db, course, "Final", 65)
    course = fresh(db, user, course)
    line = project(course, components, "x").lines[0]
    assert (line.average, line.replaced_by) == (70.0, None)


def test_different_weights_project_differently(db, user):
    course = make_course(db, user.id, "MATH 200", category_weights={"Midterm": 40.0, "Final": 60.0})
    mark(db, course, "Midterm", 90)
    mark(db, course, "Final", 70)
    course = fresh(db, user, course)
    a = project(course, own_components(course), "A")
    b = project(course, [SchemeComponent(category="Midterm", weight=20),
                         SchemeComponent(category="Final", weight=80)], "B")
    assert (a.average, b.average) == (78.0, 74.0)  # 36 + 42; 18 + 56


def test_bonus_adds_on_top_in_a_scheme_too(db, user):
    course = make_course(db, user.id, "STAT 200", category_weights={"Final": 100.0})
    mark(db, course, "Final", 70)
    mark(db, course, "Bonus", 100)
    course = fresh(db, user, course)
    result = project(course, [SchemeComponent(category="Final", weight=100),
                              SchemeComponent(category="Bonus", weight=5)], "bonus")
    assert result.average == 75.0


# --- the comparison and the rows -------------------------------------------

def test_the_comparison_names_a_better_scheme(db, user):
    course = make_course(db, user.id, "PHYS 100", category_weights={"Midterm": 40.0, "Final": 60.0})
    mark(db, course, "Midterm", 90)
    mark(db, course, "Final", 70)
    worse = create_scheme(db, user.id, course.id, scheme({"category": "Midterm", "weight": 20},
                                                         {"category": "Final", "weight": 80}, label="Worse"))
    assert compare(db, user.id, course.id).best_id is None
    better = create_scheme(db, user.id, course.id, scheme({"category": "Midterm", "weight": 60},
                                                          {"category": "Final", "weight": 40}, label="Better"))
    result = compare(db, user.id, course.id)
    assert [s.label for s in result.schemes] == ["Worse", "Better"]
    assert result.best_id == better.id and worse.id != better.id


def test_editing_and_deleting(db, user):
    course = make_course(db, user.id, "CHEM 100", category_weights={"Final": 100.0})
    made = create_scheme(db, user.id, course.id, scheme({"category": "Final", "weight": 100}))
    edited = update_scheme(db, user.id, course.id, made.id, scheme({"category": "Final", "weight": 90},
                                                                   label="Renamed"))
    assert (edited.label, edited.components[0].weight) == ("Renamed", 90)
    assert delete_scheme(db, user.id, course.id, made.id) is True
    assert delete_scheme(db, user.id, course.id, made.id) is False


def test_someone_elses_course_or_scheme_is_not_found(db, user):
    course = make_course(db, user.id, "ECON 100", category_weights={"Final": 100.0})
    made = create_scheme(db, user.id, course.id, scheme({"category": "Final", "weight": 100}))
    other = make_user(db, "other@example.com")
    theirs = make_course(db, other.id, "ECON 101", category_weights={"Final": 100.0})
    assert compare(db, other.id, course.id) is None
    assert create_scheme(db, other.id, course.id, scheme({"category": "Final", "weight": 100})) is None
    assert update_scheme(db, other.id, course.id, made.id, scheme({"category": "Final", "weight": 1})) is None
    # A scheme reached through a course it does not belong to.
    assert update_scheme(db, other.id, theirs.id, made.id, scheme({"category": "Final", "weight": 1})) is None
    assert delete_scheme(db, other.id, theirs.id, made.id) is False
    assert db.query(GradingSchemeModel).filter(GradingSchemeModel.id == made.id).one().components[0]["weight"] == 100


def test_deleting_the_course_takes_its_schemes(db, user):
    course = make_course(db, user.id, "BIOL 100", category_weights={"Final": 100.0})
    create_scheme(db, user.id, course.id, scheme({"category": "Final", "weight": 100}))
    delete_course(db, user.id, course.id)
    assert db.query(GradingSchemeModel).count() == 0


def test_a_scheme_is_validated():
    with pytest.raises(ValueError, match="once"):
        scheme({"category": "Final", "weight": 50}, {"category": "Final", "weight": 50})
    with pytest.raises(ValueError, match="replace itself"):
        scheme({"category": "Final", "weight": 100, "replace_with": "Final"})
    with pytest.raises(ValueError, match="more than 200"):
        scheme(*({"category": c, "weight": 100} for c in ("Final", "Midterm", "Quiz")))


@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_routes(db, user, client):
    course = make_course(db, user.id, "CPSC 999", category_weights={"Final": 100.0})
    base = f"/api/grades/{user.id}/courses/{course.id}/schemes"
    body = {"label": "Option B", "components": [{"category": "Final", "weight": 100}]}
    made = client.post(base, json=body).json()
    assert client.get(base).json()["schemes"][0]["label"] == "Option B"
    assert client.put(f"{base}/{made['id']}", json={**body, "label": "Option C"}).json()["label"] == "Option C"
    assert client.post(base, json={"label": "x", "components": []}).status_code == 422
    assert client.delete(f"{base}/{made['id']}").json() == {"deleted": True}
    assert client.delete(f"{base}/{made['id']}").status_code == 404


def test_weights_past_100_are_bonus_by_another_route_in_a_scheme_too(db, user):
    """A course marked out of 110%: the denominator stays 100, as on the course."""
    course = make_course(db, user.id, "CPSC 301", category_weights={"Assignment": 50.0, "Final": 60.0})
    mark(db, course, "Assignment", 80)
    mark(db, course, "Final", 90)
    course = fresh(db, user, course)
    # (80 x 50 + 90 x 60) / 100 = 94, not / 110 = 85.45.
    assert calculate_current_average(course) == 94.0
    assert project(course, own_components(course), "own").average == 94.0
