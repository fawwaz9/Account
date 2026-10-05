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


# ------------------------------------------------- below target, what next --
# Phase 1 item 2: the Attention line now says what the final has to do.

def _below(db, user, code="CPSC 221", **overrides):
    from app._database.models import GradeModel
    import uuid as _uuid

    course = bucketed(make_course(db, user.id, code, target_grade=85.0, **overrides), CURRENT)
    # Assignments 50%, all marked at 70%: average 70, final worth the other 50.
    db.add(GradeModel(id=_uuid.uuid4(), course_id=course.id, name="A1", score=70.0, max_score=100.0,
                      category="Assignment", weight=1.0))
    db.commit()
    db.refresh(course)
    course.average = 70.0
    return course


def test_below_target_says_what_the_final_needs(db, user):
    course = _below(db, user)
    [item] = [i for i in collect_attention([course], 90.0) if i.kind == "below_target"]
    # (85 - 70 x 0.5) / 0.5 = 100: reachable, exactly.
    assert item.message == "at 70% against a 85% target; needs 100% on the final"


def test_below_target_says_when_the_final_cannot_save_it(db, user):
    course = _below(db, user)
    course.target_grade = 90.0
    [item] = [i for i in collect_attention([course], 90.0) if i.kind == "below_target"]
    assert item.message.endswith("; out of reach even with 100% on the final")


def test_below_target_says_nothing_of_a_final_already_marked_or_absent(db, user):
    from app._database.models import GradeModel
    import uuid as _uuid

    marked = _below(db, user)
    db.add(GradeModel(id=_uuid.uuid4(), course_id=marked.id, name="Final", score=60.0,
                      max_score=100.0, category="Final", weight=1.0))
    db.commit()
    db.refresh(marked)
    marked.average = 70.0
    none = _below(db, user, code="CPSC 213", no_final=True)
    for course in (marked, none):
        [item] = [i for i in collect_attention([course], 90.0) if i.kind == "below_target"]
        assert item.message == "at 70% against a 85% target"
