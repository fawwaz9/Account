"""A category the student is quietly worse at than their own average.

Most of what can go wrong here is a false positive: a category weak in only
one course, a bonus category flagged as a loss, a dropped mark counted against
the student. Each guard is mutation-tested by loosening it and confirming a
finding that should be suppressed comes back instead.
"""
import uuid

import pytest

from app.Grades.schemas.blind_spot import BLIND_SPOT_BANDS
from app.Grades.schemas.grade import GradeCreate
from app.Grades.services.blind_spot_service import category_blind_spots, severity_for
from app.Grades.services.grade_service import add_grade
from app.Grades.utils.enums import GradeCategory
from tests.conftest import make_course


def mark(db, user, course, category, score, max_score=100.0, excluded=False):
    add_grade(db, user.id, course.id, GradeCreate(
        name=f"{category} item", score=score, max_score=max_score,
        category=category, excluded=excluded,
    ))


def test_a_category_worse_in_two_courses_is_reported(db, user):
    course_a = make_course(db, user.id, "AAAA 100", category_weights={"Assignment": 50.0, "Lab": 50.0})
    course_b = make_course(db, user.id, "BBBB 100", category_weights={"Assignment": 50.0, "Lab": 50.0})

    mark(db, user, course_a, GradeCategory.ASSIGNMENT.value, 90)
    mark(db, user, course_a, GradeCategory.LAB.value, 60)
    mark(db, user, course_b, GradeCategory.ASSIGNMENT.value, 88)
    mark(db, user, course_b, GradeCategory.LAB.value, 62)

    found = category_blind_spots(db, user.id)

    assert len(found) == 1
    spot = found[0]
    assert spot.category == "Lab"
    assert spot.overall_average == 75.0
    assert spot.average == 61.0
    assert spot.gap == 14.0
    assert spot.severity == "severe"
    assert spot.course_count == 2
    assert spot.item_count == 2
    assert spot.course_codes == ["AAAA 100", "BBBB 100"]


def test_a_category_weak_in_only_one_course_is_not_reported(db, user):
    course_a = make_course(db, user.id, "AAAA 100", category_weights={"Assignment": 50.0, "Lab": 50.0})
    course_b = make_course(db, user.id, "BBBB 100", category_weights={"Assignment": 50.0})

    mark(db, user, course_a, GradeCategory.ASSIGNMENT.value, 90)
    mark(db, user, course_a, GradeCategory.LAB.value, 60)
    mark(db, user, course_b, GradeCategory.ASSIGNMENT.value, 90)

    assert category_blind_spots(db, user.id) == []


def test_a_category_at_or_above_the_overall_average_is_not_reported(db, user):
    course_a = make_course(db, user.id, "AAAA 100", category_weights={"Assignment": 50.0, "Lab": 50.0})
    course_b = make_course(db, user.id, "BBBB 100", category_weights={"Assignment": 50.0, "Lab": 50.0})

    for course in (course_a, course_b):
        mark(db, user, course, GradeCategory.ASSIGNMENT.value, 80)
        mark(db, user, course, GradeCategory.LAB.value, 80)

    assert category_blind_spots(db, user.id) == []


def test_a_gap_under_the_smallest_band_is_not_reported(db, user):
    course_a = make_course(db, user.id, "AAAA 100", category_weights={"Assignment": 50.0, "Lab": 50.0})
    course_b = make_course(db, user.id, "BBBB 100", category_weights={"Assignment": 50.0, "Lab": 50.0})

    for course in (course_a, course_b):
        mark(db, user, course, GradeCategory.ASSIGNMENT.value, 80)
        mark(db, user, course, GradeCategory.LAB.value, 79)

    assert category_blind_spots(db, user.id) == []


def test_bonus_is_never_reported_as_a_blind_spot(db, user):
    course_a = make_course(db, user.id, "AAAA 100", category_weights={"Assignment": 100.0, "Bonus": 5.0})
    course_b = make_course(db, user.id, "BBBB 100", category_weights={"Assignment": 100.0, "Bonus": 5.0})

    for course in (course_a, course_b):
        mark(db, user, course, GradeCategory.ASSIGNMENT.value, 90)
        mark(db, user, course, GradeCategory.BONUS.value, 0, max_score=5.0)

    assert category_blind_spots(db, user.id) == []


def test_an_excluded_grade_is_never_counted(db, user):
    course_a = make_course(db, user.id, "AAAA 100", category_weights={"Assignment": 50.0, "Lab": 50.0})
    course_b = make_course(db, user.id, "BBBB 100", category_weights={"Assignment": 50.0, "Lab": 50.0})

    for course in (course_a, course_b):
        mark(db, user, course, GradeCategory.ASSIGNMENT.value, 90)
    mark(db, user, course_a, GradeCategory.LAB.value, 60)
    # Dropped: would otherwise pull Lab below Assignment and trigger a finding.
    mark(db, user, course_b, GradeCategory.LAB.value, 0, excluded=True)

    assert category_blind_spots(db, user.id) == []


def test_an_unmarked_item_is_ignored(db, user):
    course_a = make_course(db, user.id, "AAAA 100", category_weights={"Assignment": 50.0, "Lab": 50.0})
    course_b = make_course(db, user.id, "BBBB 100", category_weights={"Assignment": 50.0, "Lab": 50.0})

    for course in (course_a, course_b):
        mark(db, user, course, GradeCategory.ASSIGNMENT.value, 90)
        add_grade(db, user.id, course.id, GradeCreate(
            name="Not marked yet", score=None, max_score=100.0, category=GradeCategory.LAB.value,
        ))

    assert category_blind_spots(db, user.id) == []


def test_a_transfer_credit_course_contributes_nothing(db, user):
    course_a = make_course(db, user.id, "AAAA 100", category_weights={"Assignment": 50.0, "Lab": 50.0})
    course_b = make_course(
        db, user.id, "BBBB 100", category_weights={"Assignment": 50.0, "Lab": 50.0}, transfer_credit=True,
    )

    mark(db, user, course_a, GradeCategory.ASSIGNMENT.value, 90)
    mark(db, user, course_a, GradeCategory.LAB.value, 60)
    mark(db, user, course_b, GradeCategory.ASSIGNMENT.value, 90)
    mark(db, user, course_b, GradeCategory.LAB.value, 60)

    # Only one graded course now has Lab marks, so the two-course guard applies.
    assert category_blind_spots(db, user.id) == []


def test_severity_bands():
    assert severity_for(1.99) is None
    assert severity_for(2.0) == "mild"
    assert severity_for(4.99) == "mild"
    assert severity_for(5.0) == "moderate"
    assert severity_for(9.99) == "moderate"
    assert severity_for(10.0) == "severe"
    assert severity_for(-3.0) is None


def test_bands_cover_the_documented_ranges():
    assert BLIND_SPOT_BANDS["mild"] == (2.0, 5.0)
    assert BLIND_SPOT_BANDS["moderate"] == (5.0, 10.0)


def test_unknown_user_returns_none(db):
    assert category_blind_spots(db, uuid.uuid4()) is None


def test_no_marked_grades_returns_empty_list(db, user):
    make_course(db, user.id, "AAAA 100")
    assert category_blind_spots(db, user.id) == []
