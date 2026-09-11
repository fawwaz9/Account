"""What each course flag removes a course from.

Three flags, each subtracting a course from a different rule, and the rules
overlap -- a transfer credit still counts credits, an archived course still
counts in the average. Getting one wrong moves a number on the dashboard
quietly, which is why each rule is pinned separately here.
"""
from app.Grades.services.dash_services import (
    calculate_cgpa,
    calculate_cumulative_average,
    collect_attention,
    completed_credits_by_kind,
    credits_by_state,
)
from app.Grades.utils.terms import CURRENT, PAST
from conftest import make_course


def bucketed(course, bucket=PAST):
    """Courses arrive at these rules with term_bucket already attached."""
    course.term_bucket = bucket
    return course


def finished(db, user, code, **overrides):
    overrides.setdefault("final_grade", 80.0)
    overrides.setdefault("credits", 3.0)
    return bucketed(make_course(db, user.id, code, **overrides))


# --------------------------------------------------------- transfer credit --

def test_a_transfer_credit_counts_credits(db, user):
    courses = [finished(db, user, "MATH 100", transfer_credit=True, final_grade=0.0)]

    completed, in_progress = credits_by_state(courses)

    assert (completed, in_progress) == (3.0, 0.0)


def test_a_transfer_credit_counts_credits_even_in_the_current_term(db, user):
    """The credit is already granted; there is no term to wait out."""
    course = make_course(db, user.id, "MATH 100", transfer_credit=True, final_grade=0.0)
    courses = [bucketed(course, CURRENT)]

    completed, in_progress = credits_by_state(courses)

    assert (completed, in_progress) == (3.0, 0.0)


def test_a_transfer_credit_stays_out_of_the_average(db, user):
    """Otherwise it reads as a zero, which is the reason the flag exists."""
    courses = [
        finished(db, user, "CPSC 221", final_grade=90.0),
        finished(db, user, "MATH 100", transfer_credit=True, final_grade=0.0),
    ]

    assert calculate_cumulative_average(courses) == 90.0
    assert calculate_cgpa(courses) == 4.33


def test_a_transfer_credit_raises_nothing_to_act_on(db, user):
    """It is past, has no final grade, and none of that is a problem."""
    courses = [finished(db, user, "MATH 100", transfer_credit=True, final_grade=0.0)]

    assert collect_attention(courses, 90.0) == []


# ---------------------------------------------------------------- no final --

def test_a_course_with_no_final_stops_asking_for_one(db, user):
    courses = [finished(db, user, "CPSC 310", no_final=True, final_grade=0.0)]

    assert collect_attention(courses, 90.0) == []


def test_a_course_that_does_have_a_final_still_asks_for_it(db, user):
    courses = [finished(db, user, "CPSC 310", final_grade=0.0)]

    kinds = [item.kind for item in collect_attention(courses, 90.0)]
    assert "missing_final" in kinds


# ---------------------------------------------------------------- archived --

def test_an_archived_course_stops_counting_toward_credits(db, user):
    courses = [
        finished(db, user, "CPSC 221"),
        finished(db, user, "ENGL 112", archived=True),
    ]

    completed, _ = credits_by_state(courses)

    assert completed == 3.0


def test_an_archived_course_still_counts_in_the_average(db, user):
    """Archiving forgets the credit, not the mark."""
    courses = [
        finished(db, user, "CPSC 221", final_grade=90.0),
        finished(db, user, "ENGL 112", final_grade=70.0, archived=True),
    ]

    assert calculate_cumulative_average(courses) == 80.0


def test_an_archived_course_is_out_of_the_required_elective_split(db, user):
    """Or the split would total more than the credits it is splitting."""
    courses = [
        finished(db, user, "CPSC 221", required=True),
        finished(db, user, "ENGL 112", required=False, archived=True),
    ]

    assert completed_credits_by_kind(courses) == (3.0, 0.0)


# ------------------------------------------------------------ they combine --

def test_an_archived_transfer_credit_counts_for_nothing(db, user):
    courses = [finished(db, user, "MATH 100", transfer_credit=True, archived=True, final_grade=0.0)]

    assert credits_by_state(courses) == (0.0, 0.0)
    assert calculate_cumulative_average(courses) == 0.0
