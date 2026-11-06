"""Subcategory weights (D29): how a category's weight is shared between its items.

Two rules. With no subcategory weights, every item in a category counts the same,
whatever it is marked out of -- not by points, as before. With them, each item
counts by its own share, and the shares must add up to the category's weight. The
second rule is a hard limit, so every change that could break it repairs it: an
item joins a split category at 0%, one that leaves gives its share to the rest in
proportion, and a change to the category's weight scales the split.
"""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.main
from app._database.db import get_db
from app._database.models import Base, CourseCategoryWeightModel, CourseModel, GradeModel, UserModel
from app.Auth.dependencies import get_current_user
from app.Grades.schemas.grade import GradeCreate, GradeUpdate
from app.Grades.services.course_service import attach_category_averages
from app.Grades.services.grade_service import (
    add_grade,
    add_grades_bulk,
    calculate_current_average,
    calculate_grade_band,
    calculate_grade_category_average,
    calculate_required_final,
    delete_grade,
    get_user_course,
    project_course,
    set_subcategory_weights,
    update_category_weights,
    update_grade,
)
from app.Grades.utils import scheme_math
from app.Grades.utils.enums import GradeCategory
from app.Grades.utils.subcategory import spread
from conftest import make_course


def mark(db, course, category, name, got, out_of, share=None, excluded=False):
    """Add a grade straight to the table and return it."""
    grade = GradeModel(
        id=uuid.uuid4(), course_id=course.id, name=name, category=category,
        score=got, max_score=out_of, weight=0.0, subcategory_weight=share, excluded=excluded,
    )
    db.add(grade)
    db.commit()
    db.refresh(course)
    return grade


def shares(db, user, course, category="Midterm"):
    """Return name -> stored subcategory weight for a category, read fresh."""
    db.expire_all()
    fresh = get_user_course(db, user.id, course.id)
    return {g.name: g.subcategory_weight for g in fresh.grades if g.category == category}


def three_midterms(db, user, marks=((48, 52), (40, 80), (27, 30)), split=(10.0, 5.0, 15.0)):
    """The owner's example: midterms worth 30%, split 10/5/15."""
    course = make_course(db, user.id, f"MATH {uuid.uuid4().hex[:4]}", category_weights={"Midterm": 30.0, "Final": 70.0})
    grades = [
        mark(db, course, "Midterm", f"M{i + 1}", got, out_of, share)
        for i, ((got, out_of), share) in enumerate(zip(marks, split))
    ]
    return course, grades


# --------------------------------------------------------------------------
# The rule
# --------------------------------------------------------------------------

def test_with_no_split_every_item_counts_the_same(db, user):
    """5/10 and 90/100 is 50% and 90%: 70, not the 86.36 points would give."""
    course = make_course(db, user.id, "COSC 101", category_weights={"Quiz": 100.0})
    mark(db, course, "Quiz", "Q1", 5.0, 10.0)
    mark(db, course, "Quiz", "Q2", 90.0, 100.0)

    assert calculate_grade_category_average(course, "Quiz") == 70.0
    assert calculate_current_average(course) == 70.0


def test_a_split_counts_each_mark_by_its_share(db, user):
    """48/52 at 10%, 40/80 at 5%, 27/30 at 15%: 84.1, where points gave 71."""
    course, _ = three_midterms(db, user)

    assert calculate_grade_category_average(course, "Midterm") == 84.1


def test_the_points_on_the_course_page_use_the_same_shares(db, user):
    course, _ = three_midterms(db, user)

    attach_category_averages(course)
    # 84.1026% of 30.
    assert course.category_points["Midterm"] == 25.23


def test_every_reader_agrees_with_the_one_engine(db, user):
    """The average, the projection, the scheme engine and the required final."""
    course, _ = three_midterms(db, user)
    mark(db, course, "Final", "Final", None, 100.0)

    live = scheme_math.category_average(course, "Midterm")[0]
    assert calculate_grade_category_average(course, "Midterm") == live
    assert calculate_current_average(course) == live
    # Nothing outstanding in the midterms, so the final alone moves the projection.
    assert project_course(course, 0.0) == round(live * 0.30, 2)
    needed = calculate_required_final(None, user.id, course.id, 80.0, course=course)["needed"]
    assert needed == round((80.0 - live * 0.30) / 0.70, 2)


def test_an_item_at_0_percent_counts_for_nothing(db, user):
    course, _ = three_midterms(db, user, marks=((48, 52), (40, 80), (27, 30)), split=(10.0, 20.0, 0.0))
    mark(db, course, "Midterm", "M4", 0.0, 50.0, 0.0)

    # (92.31*10 + 50*20) / 30; M3 and M4 sit at 0% and change nothing.
    assert calculate_grade_category_average(course, "Midterm") == 64.1


def test_a_category_marked_only_at_0_percent_is_unknown_not_zero(db, user):
    course = make_course(db, user.id, "COSC 102", category_weights={"Midterm": 30.0, "Final": 70.0})
    mark(db, course, "Midterm", "M1", None, 50.0, 30.0)
    mark(db, course, "Midterm", "M2", 10.0, 50.0, 0.0)
    mark(db, course, "Final", "Final", 80.0, 100.0)

    # The midterms are unmarked where it matters, so only the final counts.
    assert calculate_current_average(course) == 80.0


def test_a_dropped_item_keeps_its_share_and_the_rest_count_for_it(db, user):
    course, grades = three_midterms(db, user)
    grades[1].excluded = True
    db.commit()
    db.refresh(course)

    # (92.31*10 + 90*15) / 25.
    assert calculate_grade_category_average(course, "Midterm") == 90.92
    assert shares(db, user, course)["M2"] == 5.0


def test_drop_lowest_drops_by_percentage_and_the_rest_share(db, user):
    course, _ = three_midterms(db, user)

    average, dropped = scheme_math.category_average(course, "Midterm", drop_lowest=1)
    assert dropped == 1
    # M2's 50% goes; (92.31*10 + 90*15) / 25.
    assert average == 90.92


def test_an_unmarked_item_at_0_percent_is_not_outstanding(db, user):
    course, _ = three_midterms(db, user)
    mark(db, course, "Midterm", "M4", None, 40.0, 0.0)
    mark(db, course, "Final", "Final", 75.0, 100.0)

    band = calculate_grade_band(db, user.id, course.id)
    assert band["outstanding_items"] == 0
    assert band["settled"] is True


# --------------------------------------------------------------------------
# Keeping it adding up
# --------------------------------------------------------------------------

def test_a_new_item_joins_a_split_category_at_0_percent(db, user):
    course, _ = three_midterms(db, user)

    added = add_grade(db, user.id, course.id, GradeCreate(name="M4", category=GradeCategory.MIDTERM, max_score=40.0))

    assert added.subcategory_weight == 0.0
    assert sum(shares(db, user, course).values()) == 30.0


def test_a_new_item_in_an_even_category_stays_even(db, user):
    course = make_course(db, user.id, "COSC 103", category_weights={"Quiz": 20.0, "Final": 80.0})
    mark(db, course, "Quiz", "Q1", 5.0, 10.0)

    added = add_grade(db, user.id, course.id, GradeCreate(name="Q2", category=GradeCategory.QUIZ, max_score=10.0))

    assert added.subcategory_weight is None


def test_several_new_items_all_join_at_0_percent(db, user):
    course, _ = three_midterms(db, user)

    added = add_grades_bulk(db, user.id, course.id, [
        GradeCreate(name="M4", category=GradeCategory.MIDTERM, max_score=40.0),
        GradeCreate(name="M5", category=GradeCategory.MIDTERM, max_score=40.0),
        GradeCreate(name="Final", category=GradeCategory.FINAL, max_score=100.0),
    ])

    assert [g.subcategory_weight for g in added] == [0.0, 0.0, None]


def test_deleting_an_item_shares_its_weight_in_proportion(db, user):
    """10/5/15 without the 5 is 10/15 of 30: 12 and 18."""
    course, grades = three_midterms(db, user)

    delete_grade(db, user.id, course.id, grades[1].id)

    assert shares(db, user, course) == {"M1": 12.0, "M3": 18.0}


def test_deleting_the_only_weighted_item_shares_the_rest_evenly(db, user):
    """No proportion to keep among 0s, so the weight is split evenly."""
    course, grades = three_midterms(db, user, split=(30.0, 0.0, 0.0))

    delete_grade(db, user.id, course.id, grades[0].id)

    assert shares(db, user, course) == {"M2": 15.0, "M3": 15.0}


def test_deleting_from_an_even_category_leaves_it_even(db, user):
    course = make_course(db, user.id, "COSC 104", category_weights={"Quiz": 20.0, "Final": 80.0})
    first = mark(db, course, "Quiz", "Q1", 5.0, 10.0)
    mark(db, course, "Quiz", "Q2", 9.0, 10.0)

    delete_grade(db, user.id, course.id, first.id)

    assert shares(db, user, course, "Quiz") == {"Q2": None}


def test_moving_an_item_out_rebalances_the_old_and_stays_even_in_the_new(db, user):
    course, grades = three_midterms(db, user)
    mark(db, course, "Quiz", "Q1", 8.0, 10.0)

    update_grade(db, user.id, course.id, grades[1].id, GradeUpdate(category=GradeCategory.QUIZ))

    assert shares(db, user, course) == {"M1": 12.0, "M3": 18.0}
    assert shares(db, user, course, "Quiz") == {"Q1": None, "M2": None}


def test_moving_an_item_into_a_split_category_lands_at_0(db, user):
    course, _ = three_midterms(db, user)
    stray = mark(db, course, "Quiz", "Q1", 8.0, 10.0)

    update_grade(db, user.id, course.id, stray.id, GradeUpdate(category=GradeCategory.MIDTERM))

    assert shares(db, user, course)["Q1"] == 0.0
    assert sum(shares(db, user, course).values()) == 30.0


def test_an_edit_that_keeps_the_category_keeps_the_share(db, user):
    course, grades = three_midterms(db, user)

    update_grade(db, user.id, course.id, grades[1].id, GradeUpdate(category=GradeCategory.MIDTERM, score=60.0))

    assert shares(db, user, course)["M2"] == 5.0


def test_changing_the_category_weight_scales_the_split(db, user):
    """30 to 36 takes 10/5/15 to 12/6/18."""
    course, _ = three_midterms(db, user)

    update_category_weights(db, user.id, course.id, {GradeCategory.MIDTERM: 36.0, GradeCategory.FINAL: 64.0})

    assert shares(db, user, course) == {"M1": 12.0, "M2": 6.0, "M3": 18.0}


def test_a_category_weight_of_0_clears_the_split(db, user):
    course, _ = three_midterms(db, user)

    update_category_weights(db, user.id, course.id, {GradeCategory.MIDTERM: 0.0})

    assert set(shares(db, user, course).values()) == {None}


def test_changing_another_category_leaves_the_split_alone(db, user):
    course, _ = three_midterms(db, user)

    update_category_weights(db, user.id, course.id, {GradeCategory.FINAL: 60.0})

    assert shares(db, user, course) == {"M1": 10.0, "M2": 5.0, "M3": 15.0}


def test_a_spread_adds_up_to_the_cent():
    """Three thirds of 20 can't all be 6.67; the largest takes the remainder."""
    parts = spread(20.0, [10.0, 10.0, 10.0])

    assert round(sum(parts), 2) == 20.0
    assert sorted(parts) == [6.66, 6.67, 6.67]


# --------------------------------------------------------------------------
# Setting a split
# --------------------------------------------------------------------------

def test_a_split_that_adds_up_is_kept_and_moves_the_average(db, user):
    course, grades = three_midterms(db, user, split=(None, None, None))
    # Even: (92.31 + 50 + 90) / 3.
    assert calculate_grade_category_average(course, "Midterm") == 77.44

    set_subcategory_weights(db, user.id, course.id, "Midterm", {
        grades[0].id: 10.0, grades[1].id: 5.0, grades[2].id: 15.0,
    })

    assert shares(db, user, course) == {"M1": 10.0, "M2": 5.0, "M3": 15.0}
    db.expire_all()
    assert get_user_course(db, user.id, course.id).average == 84.1


def test_a_split_that_does_not_add_up_is_refused(db, user):
    """The hard limit: 10 + 5 + 10 is 25, not 30, and nothing is written."""
    course, grades = three_midterms(db, user, split=(None, None, None))

    with pytest.raises(ValueError, match="must add up to Midterm's 30%; these add up to 25%"):
        set_subcategory_weights(db, user.id, course.id, "Midterm", {
            grades[0].id: 10.0, grades[1].id: 5.0, grades[2].id: 10.0,
        })

    db.rollback()
    assert set(shares(db, user, course).values()) == {None}


def test_a_split_must_name_every_item_and_only_those(db, user):
    course, grades = three_midterms(db, user, split=(None, None, None))

    with pytest.raises(ValueError, match="every item"):
        set_subcategory_weights(db, user.id, course.id, "Midterm", {grades[0].id: 10.0, grades[1].id: 20.0})
    with pytest.raises(ValueError, match="every item"):
        set_subcategory_weights(db, user.id, course.id, "Midterm", {
            grades[0].id: 10.0, grades[1].id: 5.0, grades[2].id: 10.0, uuid.uuid4(): 5.0,
        })


def test_a_category_with_no_weight_cannot_be_split(db, user):
    course = make_course(db, user.id, "COSC 105", category_weights={"Quiz": 0.0, "Final": 100.0})
    quiz = mark(db, course, "Quiz", "Q1", 5.0, 10.0)

    with pytest.raises(ValueError, match="no weight to split"):
        set_subcategory_weights(db, user.id, course.id, "Quiz", {quiz.id: 0.0})


def test_a_dropped_item_needs_a_share_too(db, user):
    """It keeps its place in the split, so it must be named."""
    course, grades = three_midterms(db, user, split=(None, None, None))
    grades[2].excluded = True
    db.commit()

    with pytest.raises(ValueError, match="every item"):
        set_subcategory_weights(db, user.id, course.id, "Midterm", {grades[0].id: 20.0, grades[1].id: 10.0})


def test_clearing_a_split_shares_the_weight_evenly_again(db, user):
    course, _ = three_midterms(db, user)

    set_subcategory_weights(db, user.id, course.id, "Midterm", None)

    assert set(shares(db, user, course).values()) == {None}
    db.expire_all()
    assert get_user_course(db, user.id, course.id).average == 77.44


# --------------------------------------------------------------------------
# The route
# --------------------------------------------------------------------------

@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_route_sets_a_split_and_returns_the_grades(db, user, client):
    course, grades = three_midterms(db, user, split=(None, None, None))
    url = f"/api/grades/{user.id}/courses/{course.id}/subcategory-weights"

    done = client.put(url, json={"category": "Midterm", "weights": {
        str(grades[0].id): 10, str(grades[1].id): 5, str(grades[2].id): 15,
    }})

    assert done.status_code == 200, done.text
    assert {g["name"]: g["subcategory_weight"] for g in done.json()} == {"M1": 10.0, "M2": 5.0, "M3": 15.0}


def test_the_route_refuses_a_split_that_does_not_add_up(db, user, client):
    course, grades = three_midterms(db, user, split=(None, None, None))
    url = f"/api/grades/{user.id}/courses/{course.id}/subcategory-weights"

    refused = client.put(url, json={"category": "Midterm", "weights": {
        str(grades[0].id): 10, str(grades[1].id): 10, str(grades[2].id): 15,
    }})

    assert refused.status_code == 400
    assert "35%" in refused.json()["detail"]


def test_the_route_refuses_a_share_over_100(db, user, client):
    course, grades = three_midterms(db, user, split=(None, None, None))
    url = f"/api/grades/{user.id}/courses/{course.id}/subcategory-weights"

    refused = client.put(url, json={"category": "Midterm", "weights": {str(grades[0].id): 130}})

    assert refused.status_code == 422


def test_a_grade_read_carries_its_share(db, user, client):
    course, _ = three_midterms(db, user)

    read = client.get(f"/api/grades/{user.id}/courses/{course.id}")

    assert read.status_code == 200, read.text
    by_name = {g["name"]: g["subcategory_weight"] for g in read.json()["grades"]}
    assert by_name == {"M1": 10.0, "M2": 5.0, "M3": 15.0}


# --------------------------------------------------------------------------
# Bringing stored averages over
# --------------------------------------------------------------------------

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "recompute_averages.py"


def run_recompute(url, *args):
    """Run the recompute script in its own process, as the usage report's tests do."""
    env = {k: v for k, v in os.environ.items() if k != "RECOMPUTE_URL"}
    env["RECOMPUTE_URL"] = url
    return subprocess.run([sys.executable, str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=60)


def test_the_recompute_lists_first_and_writes_only_when_told(tmp_path):

    url = f"sqlite:///{tmp_path / 'recompute.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    owner = UserModel(id=uuid.uuid4(), name="o", email="o@example.com", email_verified=True)
    mixed = CourseModel(id=uuid.uuid4(), user_id=owner.id, code="COSC 101", name="c", semester="Fall", year=1,
                        credits=3.0, required=True, final_grade=0.0, average=86.36)
    settled = CourseModel(id=uuid.uuid4(), user_id=owner.id, code="COSC 102", name="c", semester="Fall", year=1,
                          credits=3.0, required=True, final_grade=0.0, average=80.0)
    session.add_all([owner, mixed, settled])
    session.flush()
    session.add_all([
        CourseCategoryWeightModel(course_id=mixed.id, category="Quiz", weight=100.0),
        CourseCategoryWeightModel(course_id=settled.id, category="Quiz", weight=100.0),
        GradeModel(id=uuid.uuid4(), course_id=mixed.id, name="Q1", category="Quiz", score=5.0, max_score=10.0, weight=100.0),
        GradeModel(id=uuid.uuid4(), course_id=mixed.id, name="Q2", category="Quiz", score=90.0, max_score=100.0, weight=100.0),
        GradeModel(id=uuid.uuid4(), course_id=settled.id, name="Q1", category="Quiz", score=80.0, max_score=100.0, weight=100.0),
    ])
    session.commit()

    listed = run_recompute(url)
    assert listed.returncode == 0, listed.stderr
    assert "COSC 101" in listed.stdout and "86.36 ->  70.00" in listed.stdout
    assert "COSC 102" not in listed.stdout
    assert "Nothing written" in listed.stdout
    session.expire_all()
    assert session.get(CourseModel, mixed.id).average == 86.36

    applied = run_recompute(url, "--apply")
    assert applied.returncode == 0, applied.stderr
    assert "Wrote 1." in applied.stdout
    session.expire_all()
    assert session.get(CourseModel, mixed.id).average == 70.0
    assert session.get(CourseModel, settled.id).average == 80.0

    again = run_recompute(url)
    assert "Nothing to change" in again.stdout
    session.close()
    engine.dispose()


def test_the_recompute_needs_its_url():
    env = {k: v for k, v in os.environ.items() if k != "RECOMPUTE_URL"}
    done = subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)
    assert done.returncode == 2
    assert "RECOMPUTE_URL is not set" in done.stderr
