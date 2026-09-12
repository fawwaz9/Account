"""Bonus as a category that adds to a course instead of composing it.

Every other category answers "out of how much"; bonus answers "and then some".
That one difference has to be honoured in four separate places, and each of them
was wrong in a different way before this suite existed -- the denominator, the
dashboard's idea of unfinished work, the weight sanity checks, and the prediction
of what a final needs to be. One test per failure mode, because they fail
independently.
"""
import uuid

from app._database.models import GradeModel
from app.Grades.services.dash_services import get_dashboard
from app.Grades.services.grade_service import (
    bonus_contribution,
    calculate_current_average,
    calculate_required_final,
)
from app.Grades.utils.weights import weight_problems
from conftest import make_course


def score(db, course, category, name, got, out_of):
    db.add(GradeModel(
        id=uuid.uuid4(), course_id=course.id, name=name, category=category,
        score=got, max_score=out_of, weight=0.0,
    ))
    db.commit()
    db.refresh(course)
    return course


# ------------------------------------------------------------ the formula --

def test_a_course_without_bonus_is_unchanged(db, user):
    """The whole backward-compatibility claim, pinned.

    Every existing course gets Bonus at weight 0 from default_category_weights,
    so none of them may move by even a hundredth.
    """
    course = make_course(db, user.id, "CPSC 110",
                         category_weights={"Assignment": 40.0, "Final": 60.0})
    score(db, course, "Assignment", "A1", 90.0, 100.0)

    assert calculate_current_average(course) == 90.0


def test_bonus_adds_without_joining_the_denominator(db, user):
    """The defect this change exists to fix.

    Assignments 20% marked at 90%, bonus 5% marked full. Bonus counted as an
    ordinary category gives (90*20 + 100*5)/25 = 92 -- it dilutes toward its own
    score. Held out and added back it gives 90 + 5 = 95.
    """
    course = make_course(db, user.id, "CPSC 210", category_weights={
        "Assignment": 20.0, "Final": 80.0, "Bonus": 5.0,
    })
    score(db, course, "Assignment", "A1", 90.0, 100.0)
    score(db, course, "Bonus", "Extra credit", 10.0, 10.0)

    assert calculate_current_average(course) == 95.0


def test_partial_bonus_is_worth_part_of_its_weight(db, user):
    course = make_course(db, user.id, "CPSC 213", category_weights={
        "Assignment": 20.0, "Final": 80.0, "Bonus": 5.0,
    })
    score(db, course, "Assignment", "A1", 80.0, 100.0)
    score(db, course, "Bonus", "Extra credit", 5.0, 10.0)

    # Half the bonus work at 5% of the course is two and a half points.
    assert calculate_current_average(course) == 82.5


def test_bonus_is_measured_against_the_course_not_the_graded_slice(db, user):
    """A 5% bonus is five points in week two and five points in week twelve.

    Scaled to the graded weight instead, this same course would read 100 -- a
    fifth of the term marked and already showing full marks.
    """
    course = make_course(db, user.id, "CPSC 221", category_weights={
        "Assignment": 20.0, "Final": 80.0, "Bonus": 5.0,
    })
    score(db, course, "Assignment", "A1", 95.0, 100.0)
    score(db, course, "Bonus", "Extra credit", 10.0, 10.0)

    assert calculate_current_average(course) == 100.0
    assert bonus_contribution(course) == 5.0


def test_the_course_still_caps_at_one_hundred(db, user):
    course = make_course(db, user.id, "CPSC 302", category_weights={
        "Assignment": 100.0, "Bonus": 10.0,
    })
    score(db, course, "Assignment", "A1", 98.0, 100.0)
    score(db, course, "Bonus", "Extra credit", 10.0, 10.0)

    # 98 + 10 = 108, reported as 100.
    assert calculate_current_average(course) == 100.0


def test_bonus_alone_is_not_a_percentage_of_nothing(db, user):
    """Bonus marked before anything else does not divide by an empty denominator."""
    course = make_course(db, user.id, "CPSC 303", category_weights={
        "Assignment": 100.0, "Bonus": 5.0,
    })
    score(db, course, "Bonus", "Extra credit", 10.0, 10.0)

    assert calculate_current_average(course) == 5.0


def test_a_grade_over_its_max_still_lifts_its_category(db, user):
    """Bonus marks on an ordinary assignment: the older mechanism, still working."""
    course = make_course(db, user.id, "CPSC 304",
                         category_weights={"Assignment": 100.0})
    score(db, course, "Assignment", "A1", 11.0, 10.0)

    assert calculate_current_average(course) == 100.0


# ------------------------------------------------------- the sanity checks --

def test_a_missing_category_is_still_reported_behind_a_bonus(db, user):
    """95 real + 5 bonus reaches 100 only if bonus is wrongly counted."""
    course = make_course(db, user.id, "CPSC 305", category_weights={
        "Assignment": 35.0, "Final": 60.0, "Bonus": 5.0,
    })

    assert any("may be missing" in problem for problem in weight_problems(course))


def test_a_generous_bonus_is_not_a_typo(db, user):
    """100 real + 15 bonus is a correctly built course, not a slipped digit."""
    course = make_course(db, user.id, "CPSC 306", category_weights={
        "Assignment": 40.0, "Final": 60.0, "Bonus": 15.0,
    })

    assert weight_problems(course) == []


def test_bonus_cannot_stand_in_for_the_largest_category(db, user):
    """The swapped-weights check compares the final against real categories only."""
    course = make_course(db, user.id, "CPSC 307", category_weights={
        "Assignment": 98.0, "Final": 2.0, "Bonus": 30.0,
    })

    problems = weight_problems(course)

    assert any("swapped" in problem for problem in problems)
    assert not any("30%" in problem for problem in problems)


# ------------------------------------------------------------ the nagging --

def test_an_empty_bonus_is_not_unfinished_work(db, user):
    """Otherwise it sits in Attention all term as a warning nothing can clear."""
    # Lab carries the test: it is ungraded, weighted, and neither Final nor
    # Bonus, so it must still be reported. Without it both categories would be
    # excluded for their own reasons, the list would be empty, and "Bonus is
    # absent" would pass without proving anything.
    course = make_course(db, user.id, "CPSC 308", category_weights={
        "Assignment": 40.0, "Lab": 20.0, "Final": 40.0, "Bonus": 5.0,
    })
    score(db, course, "Assignment", "A1", 80.0, 100.0)

    dashboard = get_dashboard(db, user.id, target_grade=80.0)
    listed = [
        category
        for categories in dashboard.unfinished_categories_by_course.values()
        for category in categories
    ]

    assert "Lab" in listed
    assert "Bonus" not in listed


def test_required_final_ignores_an_empty_bonus(db, user):
    course = make_course(db, user.id, "CPSC 309", category_weights={
        "Assignment": 40.0, "Final": 60.0, "Bonus": 5.0,
    })
    score(db, course, "Assignment", "A1", 80.0, 100.0)

    answer = calculate_required_final(db, user.id, course.id, target_grade=80.0)

    assert "Bonus" not in answer["unfinished_categories"]


# --------------------------------------------------------- the prediction --

def test_banked_bonus_lowers_what_the_final_needs(db, user):
    """Bonus must reduce the bar, and by exactly its own contribution.

    Counted on both sides -- as marks earned and as weight to make up -- it would
    have cancelled most of its own effect out, which is the subtle version of
    this bug and the reason the two runs are compared rather than asserted flat.
    """
    weights = {"Assignment": 40.0, "Final": 60.0, "Bonus": 5.0}

    without = make_course(db, user.id, "CPSC 310", category_weights=weights)
    score(db, without, "Assignment", "A1", 70.0, 100.0)
    plain = calculate_required_final(db, user.id, without.id, target_grade=80.0)

    with_bonus = make_course(db, user.id, "CPSC 311", category_weights=weights)
    score(db, with_bonus, "Assignment", "A1", 70.0, 100.0)
    score(db, with_bonus, "Bonus", "Extra credit", 10.0, 10.0)
    lifted = calculate_required_final(db, user.id, with_bonus.id, target_grade=80.0)

    # 5 points of bonus against a final worth 60% of the course is 5/0.6 fewer
    # marks needed on the paper itself. Compared with a tolerance because both
    # figures are rounded to a cent independently, so differencing them carries
    # two roundings and can land a cent off a flat equality.
    assert abs((plain["needed"] - lifted["needed"]) - 5.0 / 0.6) < 0.02
    assert lifted["needed"] < plain["needed"]
