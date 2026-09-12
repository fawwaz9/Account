"""Marks kept on a course but left out of its arithmetic.

Professors drop the two lowest quizzes. The marks still happened, you may want
to look at them, and which ones are dropped changes as more work comes back --
so deleting them is wrong and the flag has to be reversible.

The risk is leakage: six separate places sum grades, and one that forgets the
flag shows a wrong average confidently. There is a test per place.
"""
import uuid

from app._database.models import GradeModel
from app.Grades.services.dash_services import get_dashboard
from app.Grades.services.grade_service import (
    calculate_current_average,
    calculate_grade_band,
    calculate_grade_category_average,
    calculate_required_final,
)
from conftest import make_course


def score(db, course, category, name, got, out_of, excluded=False):
    db.add(GradeModel(
        id=uuid.uuid4(), course_id=course.id, name=name, category=category,
        score=got, max_score=out_of, weight=0.0, excluded=excluded,
    ))
    db.commit()
    db.refresh(course)
    return course


def test_a_dropped_mark_leaves_the_average(db, user):
    """The headline case: drop the lowest quiz and the average rises."""
    course = make_course(db, user.id, "COSC 111",
                         category_weights={"Quiz": 100.0})
    score(db, course, "Quiz", "Q1", 90.0, 100.0)
    score(db, course, "Quiz", "Q2", 80.0, 100.0)
    score(db, course, "Quiz", "Q3", 40.0, 100.0)

    assert calculate_current_average(course) == 70.0

    lowest = next(g for g in course.grades if g.name == "Q3")
    lowest.excluded = True
    db.commit()
    db.refresh(course)

    assert calculate_current_average(course) == 85.0


def test_a_dropped_mark_leaves_its_category_average(db, user):
    course = make_course(db, user.id, "COSC 121",
                         category_weights={"Quiz": 100.0})
    score(db, course, "Quiz", "Q1", 10.0, 10.0)
    score(db, course, "Quiz", "Q2", 0.0, 10.0, excluded=True)

    assert calculate_grade_category_average(course, "Quiz") == 100.0


def test_dropping_every_mark_in_a_category_removes_the_category(db, user):
    """Not the same as the category scoring zero, which would be a fail."""
    course = make_course(db, user.id, "COSC 122",
                         category_weights={"Quiz": 50.0, "Final": 50.0})
    score(db, course, "Quiz", "Q1", 0.0, 10.0, excluded=True)
    score(db, course, "Final", "Final", 80.0, 100.0)

    # Only the final counts, so the course reads 80 rather than 40.
    assert calculate_current_average(course) == 80.0


def test_a_dropped_mark_does_not_reach_the_band(db, user):
    course = make_course(db, user.id, "COSC 210",
                         category_weights={"Quiz": 100.0})
    score(db, course, "Quiz", "Q1", 90.0, 100.0)
    score(db, course, "Quiz", "Q2", 10.0, 100.0, excluded=True)

    band = calculate_grade_band(db, user.id, course.id)
    assert band["best"] == band["worst"] == 90.0
    assert band["settled"] is True


def test_an_unmarked_dropped_item_is_not_outstanding(db, user):
    """A dropped item you will never sit should not hold the band open."""
    course = make_course(db, user.id, "COSC 211",
                         category_weights={"Quiz": 100.0})
    score(db, course, "Quiz", "Q1", 90.0, 100.0)
    score(db, course, "Quiz", "Q2", None, 100.0, excluded=True)

    band = calculate_grade_band(db, user.id, course.id)
    assert band["outstanding_items"] == 0
    assert band["settled"] is True


def test_a_dropped_mark_does_not_lower_the_required_final(db, user):
    course = make_course(db, user.id, "COSC 212",
                         category_weights={"Quiz": 50.0, "Final": 50.0})
    score(db, course, "Quiz", "Q1", 80.0, 100.0)
    plain = calculate_required_final(db, user.id, course.id, target_grade=80.0)

    score(db, course, "Quiz", "Q2", 0.0, 100.0, excluded=True)
    after = calculate_required_final(db, user.id, course.id, target_grade=80.0)

    assert after["needed"] == plain["needed"]


def test_a_category_of_only_dropped_marks_is_still_unfinished(db, user):
    """Dropping your only quiz does not mean the quizzes are done."""
    course = make_course(db, user.id, "COSC 213", category_weights={
        "Quiz": 30.0, "Lab": 30.0, "Final": 40.0,
    })
    score(db, course, "Lab", "L1", 80.0, 100.0)
    score(db, course, "Quiz", "Q1", 0.0, 10.0, excluded=True)

    dashboard = get_dashboard(db, user.id, target_grade=80.0)
    listed = [
        category
        for categories in dashboard.unfinished_categories_by_course.values()
        for category in categories
    ]
    assert "Quiz" in listed


def test_excluding_is_reversible(db, user):
    """Which marks are dropped changes as more work comes back."""
    course = make_course(db, user.id, "COSC 214",
                         category_weights={"Quiz": 100.0})
    score(db, course, "Quiz", "Q1", 90.0, 100.0)
    score(db, course, "Quiz", "Q2", 50.0, 100.0)

    low = next(g for g in course.grades if g.name == "Q2")
    low.excluded = True
    db.commit(); db.refresh(course)
    assert calculate_current_average(course) == 90.0

    low.excluded = False
    db.commit(); db.refresh(course)
    assert calculate_current_average(course) == 70.0


def test_a_dropped_bonus_mark_stops_contributing(db, user):
    from app.Grades.services.grade_service import bonus_contribution

    course = make_course(db, user.id, "COSC 215", category_weights={
        "Assignment": 100.0, "Bonus": 5.0,
    })
    score(db, course, "Assignment", "A1", 80.0, 100.0)
    score(db, course, "Bonus", "Extra", 10.0, 10.0, excluded=True)

    assert bonus_contribution(course) == 0.0
    assert calculate_current_average(course) == 80.0


def test_existing_grades_default_to_counting(db, user):
    """The whole backward-compatibility claim for the new column."""
    course = make_course(db, user.id, "COSC 216",
                         category_weights={"Quiz": 100.0})
    score(db, course, "Quiz", "Q1", 75.0, 100.0)

    assert course.grades[0].excluded is False
    assert calculate_current_average(course) == 75.0
