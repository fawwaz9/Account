"""Picking a grading scheme as a course's grade (Phase 1 D25).

The invariants first, because this is the first feature that moves a grade
figure people already rely on:

* **Nothing picked, nothing changes.** course_grade is the course's own average.
* **The course's own weights, picked as a scheme, change nothing either** --
  the stored average, the band, the required final and the cheapest path's
  projections all agree with today's engines, over many generated courses. So
  a picked scheme can only move a figure for a reason it shows.

Then the rules, with hand-computed figures, and the boundaries: a scheme is
reached only through its own course, and deleting the counting scheme puts the
course's own weights back in the same commit.
"""
import random
import uuid

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import CourseModel, GradeModel, GradingSchemeModel
from app.Auth.dependencies import get_current_user
from app.Grades.schemas.scheme import SchemeComponent, SchemeWrite
from app.Grades.services.dash_services import get_dashboard
from app.Grades.services.grade_service import (
    add_grade,
    calculate_current_average,
    calculate_grade_band,
    calculate_required_final,
    course_grade,
    get_user_course,
    project_average,
    project_course,
    required_final_under_scheme,
)
from app.Grades.schemas.grade import GradeCreate
from app.Grades.services.scheme_service import (
    compare,
    create_scheme,
    delete_scheme,
    own_components,
    set_counting,
    update_scheme,
)
from conftest import make_course, make_user


def mark(db, course, category, got, out_of=100.0, excluded=False):
    row = GradeModel(id=uuid.uuid4(), course_id=course.id, name=f"{category} {got} {uuid.uuid4().hex[:4]}",
                     category=category, score=got, max_score=out_of, weight=0.0, excluded=excluded)
    db.add(row)
    db.commit()
    return row


def fresh(db, user, course):
    db.expire_all()
    return get_user_course(db, user.id, course.id)


def scheme(*components, label="B"):
    return SchemeWrite(label=label, components=[SchemeComponent(**c) for c in components])


def stored(db, course_id):
    db.expire_all()
    return db.query(CourseModel).filter(CourseModel.id == course_id).one().average


# --- the invariants --------------------------------------------------------

def generated_courses(db, user, count=40):
    rng = random.Random(20261005)
    categories = ["Assignment", "Lab", "Quiz", "Midterm", "Project", "Final", "Bonus"]
    for n in range(count):
        chosen = rng.sample(categories, rng.randint(1, 5))
        if rng.random() < 0.7 and "Final" not in chosen:
            chosen.append("Final")
        weights = {c: float(rng.choice([5, 10, 15, 20, 25, 30, 40])) for c in chosen}
        course = make_course(db, user.id, f"GEN {n:03d}", category_weights=weights)
        for _ in range(rng.randint(0, 8)):
            category = rng.choice(chosen + ["Other"])
            out_of = float(rng.choice([10, 20, 50, 100]))
            marked = rng.random() < 0.75
            db.add(GradeModel(
                id=uuid.uuid4(), course_id=course.id, name=f"{category} {uuid.uuid4().hex[:6]}",
                category=category, score=round(rng.uniform(0, out_of * 1.1), 1) if marked else None,
                max_score=out_of, weight=0.0, excluded=rng.random() < 0.1,
            ))
        db.commit()
        yield fresh(db, user, course), rng


def test_nothing_picked_is_the_course_own_average(db, user):
    for course, _ in generated_courses(db, user, 15):
        assert course_grade(course) == calculate_current_average(course)
        assert project_course(course, 1.0) == project_average(course, 1.0)


def test_the_course_own_weights_picked_change_no_figure(db, user):
    checked_final = 0
    for course, rng in generated_courses(db, user):
        expected = {
            "average": calculate_current_average(course),
            "best": project_average(course, 1.0),
            "worst": project_average(course, 0.0),
        }
        some_grade = next(iter(course.grades), None)
        if some_grade is not None:
            expected["override"] = project_average(course, 0.5, {some_grade.id: 1.0})
        formula = None
        if course.category_weights.get("Final", 0) > 0:
            target = float(rng.choice([50, 70, 85, 95]))
            formula = calculate_required_final(None, user.id, course.id, target, course=course)

        made = create_scheme(db, user.id, course.id, scheme(
            *({"category": c.category.value, "weight": c.weight} for c in own_components(course))))
        set_counting(db, user.id, course.id, made.id)
        course = fresh(db, user, course)

        assert course.counting_scheme_id == made.id
        assert course_grade(course) == expected["average"], course.code
        assert course.average == expected["average"], course.code
        assert project_course(course, 1.0) == expected["best"], course.code
        assert project_course(course, 0.0) == expected["worst"], course.code
        if some_grade is not None:
            assert project_course(course, 0.5, {some_grade.id: 1.0}) == expected["override"], course.code
        if formula is not None and formula["needed"] <= 1000:
            under = calculate_required_final(None, user.id, course.id, target, course=course)
            assert abs(under["needed"] - max(formula["needed"], 0.0)) <= 0.02, (course.code, under, formula)
            assert under["possible"] == (0 <= max(formula["needed"], 0.0) <= 100)
            assert sorted(under["unfinished_categories"]) == sorted(formula["unfinished_categories"])
            checked_final += 1
    assert checked_final >= 15, "most generated courses must reach the required-final comparison"


# --- what a picked scheme changes ------------------------------------------

@pytest.fixture
def course(db, user):
    """Midterm 40 / Final 60, marked 90 and 70: 78 by its own weights."""
    course = make_course(db, user.id, "MATH 200", category_weights={"Midterm": 40.0, "Final": 60.0})
    mark(db, course, "Midterm", 90)
    mark(db, course, "Final", 70)
    course = fresh(db, user, course)
    course.average = calculate_current_average(course)
    db.commit()
    return course


def test_picking_moves_the_stored_grade_and_unpicking_restores_it(db, user, course):
    assert stored(db, course.id) == 78.0
    heavy_final = create_scheme(db, user.id, course.id, scheme(
        {"category": "Midterm", "weight": 20}, {"category": "Final", "weight": 80}))
    assert stored(db, course.id) == 78.0  # adding a scheme moves nothing
    result = set_counting(db, user.id, course.id, heavy_final.id)
    assert result.counting_id == heavy_final.id
    assert stored(db, course.id) == 74.0  # 18 + 56
    set_counting(db, user.id, course.id, None)
    assert stored(db, course.id) == 78.0


def test_the_dashboard_follows_the_picked_scheme(db, user, course):
    user.current_school_year, user.current_semester = 3, "Fall"
    db.commit()
    heavy_final = create_scheme(db, user.id, course.id, scheme(
        {"category": "Midterm", "weight": 20}, {"category": "Final", "weight": 80}))
    before = get_dashboard(db, user.id)
    set_counting(db, user.id, course.id, heavy_final.id)
    after = get_dashboard(db, user.id)
    # The term average: the cumulative counts finished courses only.
    assert before.semester_average == 78.0 and after.semester_average == 74.0


def test_a_mark_added_later_is_counted_by_the_scheme(db, user, course):
    drop_one = create_scheme(db, user.id, course.id, scheme(
        {"category": "Midterm", "weight": 40, "drop_lowest": 1}, {"category": "Final", "weight": 60}))
    set_counting(db, user.id, course.id, drop_one.id)
    add_grade(db, user.id, course.id, GradeCreate(name="Midterm 2", category="Midterm", score=50, max_score=100))
    # Own weights: midterms average 70 -> 28 + 42 = 70. The scheme drops the 50: 36 + 42 = 78.
    assert stored(db, course.id) == 78.0


def test_editing_the_counting_scheme_moves_the_grade_and_another_does_not(db, user, course):
    counting = create_scheme(db, user.id, course.id, scheme(
        {"category": "Midterm", "weight": 20}, {"category": "Final", "weight": 80}, label="A"))
    other = create_scheme(db, user.id, course.id, scheme(
        {"category": "Midterm", "weight": 60}, {"category": "Final", "weight": 40}, label="C"))
    set_counting(db, user.id, course.id, counting.id)
    update_scheme(db, user.id, course.id, other.id, scheme(
        {"category": "Midterm", "weight": 100}, label="C"))
    assert stored(db, course.id) == 74.0
    update_scheme(db, user.id, course.id, counting.id, scheme(
        {"category": "Midterm", "weight": 50}, {"category": "Final", "weight": 50}, label="A"))
    assert stored(db, course.id) == 80.0  # 45 + 35


def test_deleting_the_counting_scheme_puts_the_course_weights_back(db, user, course):
    counting = create_scheme(db, user.id, course.id, scheme(
        {"category": "Midterm", "weight": 20}, {"category": "Final", "weight": 80}))
    set_counting(db, user.id, course.id, counting.id)
    assert delete_scheme(db, user.id, course.id, counting.id) is True
    reloaded = fresh(db, user, course)
    assert reloaded.counting_scheme_id is None and reloaded.average == 78.0
    assert db.query(GradingSchemeModel).count() == 0


def test_a_stale_id_falls_back_to_the_course_own_weights(db, user, course):
    course.counting_scheme_id = uuid.uuid4()
    db.commit()
    assert course_grade(fresh(db, user, course)) == 78.0


# --- the projections under a scheme, by hand -------------------------------

def test_the_required_final_under_a_replacement_rule(db, user):
    """Midterm 40 (replaced by the final if higher) / Final 60, midterm 50.
    Target 80: without the rule the final needs (80 - 20) / 0.6 = 100. With it,
    a final of f >= 50 gives f across the board, so it needs 80."""
    course = make_course(db, user.id, "PHYS 101", category_weights={"Midterm": 40.0, "Final": 60.0})
    mark(db, course, "Midterm", 50)
    rule = create_scheme(db, user.id, course.id, scheme(
        {"category": "Midterm", "weight": 40, "replace_with": "Final"}, {"category": "Final", "weight": 60}))
    course = fresh(db, user, course)
    assert calculate_required_final(None, user.id, course.id, 80.0, course=course)["needed"] == 100.0
    set_counting(db, user.id, course.id, rule.id)
    answer = calculate_required_final(None, user.id, course.id, 80.0, course=fresh(db, user, course))
    assert answer == {"needed": 80.0, "possible": True, "unfinished_categories": []}


def test_the_required_final_already_reached_and_out_of_reach(db, user, course):
    counting = create_scheme(db, user.id, course.id, scheme(
        {"category": "Midterm", "weight": 90}, {"category": "Final", "weight": 10}))
    set_counting(db, user.id, course.id, counting.id)
    course = fresh(db, user, course)
    assert required_final_under_scheme(course, own(counting), 50.0)["needed"] == 0.0  # 81 with a zero final
    impossible = required_final_under_scheme(course, own(counting), 99.0)
    assert impossible["possible"] is False and impossible["needed"] > 100


def test_no_final_in_the_scheme_is_said(db, user, course):
    no_final = create_scheme(db, user.id, course.id, scheme({"category": "Midterm", "weight": 100}))
    set_counting(db, user.id, course.id, no_final.id)
    with pytest.raises(ValueError, match="no final"):
        calculate_required_final(None, user.id, course.id, 80.0, course=fresh(db, user, course))


def test_the_band_under_a_drop_rule(db, user):
    """Quizzes 50 (drop the lowest) / Final 50. Quizzes 40 and 80 marked, one
    unmarked, the final unmarked. Best: quizzes {80, 100} -> 90, final 100 -> 95.
    Worst: quizzes {40, 80, 0} drop the 0 -> 60, final 0 -> 30."""
    course = make_course(db, user.id, "STAT 300", category_weights={"Quiz": 50.0, "Final": 50.0})
    mark(db, course, "Quiz", 40)
    mark(db, course, "Quiz", 80)
    db.add(GradeModel(id=uuid.uuid4(), course_id=course.id, name="Quiz 3", category="Quiz",
                      score=None, max_score=100.0, weight=0.0))
    db.commit()
    drop = create_scheme(db, user.id, course.id, scheme(
        {"category": "Quiz", "weight": 50, "drop_lowest": 1}, {"category": "Final", "weight": 50}))
    set_counting(db, user.id, course.id, drop.id)
    band = calculate_grade_band(db, user.id, course.id)
    assert (band["best"], band["worst"], band["current"]) == (95.0, 30.0, 80.0)
    assert band["empty_categories"] == ["Final"] and band["outstanding_items"] == 1


def own(made):
    return [SchemeComponent.model_validate(c.model_dump()) for c in made.components]


# --- the boundaries --------------------------------------------------------

def test_a_scheme_is_picked_only_through_its_own_course(db, user, course):
    other_course = make_course(db, user.id, "MATH 201", category_weights={"Final": 100.0})
    theirs = create_scheme(db, user.id, other_course.id, scheme({"category": "Final", "weight": 100}))
    assert set_counting(db, user.id, course.id, theirs.id) is None
    stranger = make_user(db, "other@example.com")
    assert set_counting(db, stranger.id, course.id, None) is None
    assert fresh(db, user, course).counting_scheme_id is None


def test_the_comparison_names_the_counting_scheme(db, user, course):
    counting = create_scheme(db, user.id, course.id, scheme({"category": "Final", "weight": 100}))
    assert compare(db, user.id, course.id).counting_id is None
    set_counting(db, user.id, course.id, counting.id)
    assert compare(db, user.id, course.id).counting_id == counting.id


@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_route(db, user, course, client):
    made = create_scheme(db, user.id, course.id, scheme(
        {"category": "Midterm", "weight": 20}, {"category": "Final", "weight": 80}))
    url = f"/api/grades/{user.id}/courses/{course.id}/counting-scheme"
    picked = client.put(url, json={"scheme_id": str(made.id)})
    assert picked.status_code == 200 and picked.json()["counting_id"] == str(made.id)
    detail = client.get(f"/api/grades/{user.id}/courses/{course.id}").json()
    assert (detail["counting_scheme_id"], detail["average"]) == (str(made.id), 74.0)
    assert client.put(url, json={"scheme_id": str(uuid.uuid4())}).status_code == 404
    assert client.put(url, json={"scheme_id": None}).json()["counting_id"] is None


# --- every write of the stored average goes through the picked scheme -------

@pytest.fixture
def picked(db, user):
    """Own weights Midterm 40 / Final 60, marked 90 and 60: 72. The picked
    scheme is Midterm 20 / Final 80: 66. Each path below must store the
    scheme's figure, which always differs from the own-weights one."""
    course = make_course(db, user.id, "CHEM 300", category_weights={"Midterm": 40.0, "Final": 60.0})
    midterm = mark(db, course, "Midterm", 90)
    final = mark(db, course, "Final", 60)
    counting = create_scheme(db, user.id, course.id, scheme(
        {"category": "Midterm", "weight": 20}, {"category": "Final", "weight": 80}))
    set_counting(db, user.id, course.id, counting.id)
    assert stored(db, course.id) == 66.0
    return course, midterm, final


def test_changing_the_course_weights_keeps_the_scheme_grade(db, user, picked):
    from app.Grades.services.grade_service import update_category_weights
    course, _, _ = picked
    update_category_weights(db, user.id, course.id, {"Midterm": 50.0, "Final": 50.0})
    assert stored(db, course.id) == 66.0  # own weights would now say 75


def test_adding_marks_in_bulk_is_counted_by_the_scheme(db, user, picked):
    from app.Grades.services.grade_service import add_grades_bulk
    course, _, _ = picked
    add_grades_bulk(db, user.id, course.id, [GradeCreate(name="Final 2", category="Final", score=100, max_score=100)])
    assert stored(db, course.id) == 82.0  # finals average 80: 18 + 64 (own: 84)


def test_editing_a_mark_is_counted_by_the_scheme(db, user, picked):
    from app.Grades.schemas.grade import GradeUpdate
    from app.Grades.services.grade_service import update_grade
    course, _, final = picked
    update_grade(db, user.id, course.id, final.id, GradeUpdate(score=40))
    assert stored(db, course.id) == 50.0  # 18 + 32 (own: 60)


def test_deleting_a_mark_is_counted_by_the_scheme(db, user, picked):
    from app.Grades.services.grade_service import delete_grade
    course, _, _ = picked
    extra = mark(db, course, "Midterm", 50)
    delete_grade(db, user.id, course.id, extra.id)
    assert stored(db, course.id) == 66.0  # own: 72


def test_recording_a_score_is_counted_by_the_scheme(db, user, picked):
    from app.Grades.services.grade_service import record_grade
    course, _, _ = picked
    pending = GradeModel(id=uuid.uuid4(), course_id=course.id, name="Final 2", category="Final",
                         score=None, max_score=100.0, weight=0.0)
    db.add(pending)
    db.commit()
    record_grade(db, user.id, course.id, pending.id, 100.0)
    assert stored(db, course.id) == 82.0  # own: 84
