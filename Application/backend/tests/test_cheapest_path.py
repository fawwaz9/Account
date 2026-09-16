"""Which remaining item is worth doing next.

Leverage is a *spread*: the course average with one item at full marks minus
the same average with it at zero, every other outstanding item held constant.
That is the share of the final average the item controls, and the claim the
whole ranking rests on is that it comes out the same whatever the other items
are assumed to do -- their contribution appears in both halves and cancels.
There is a test named for exactly that.
"""
import datetime

import pytest

from app._database.models import GradeModel, TaskModel, utc_now
from app.Grades.schemas.grade import GradeCreate
from app.Grades.services.cheapest_path import cheapest_path, item_leverage
from app.Grades.services.grade_service import add_grade
from app.Grades.utils.enums import GradeSchedule
from conftest import make_course
import uuid


def course_with(db, user, weights, code="CPSC 221"):
    return make_course(db, user.id, code, category_weights=weights)


def grade(db, user, course, name, category, max_score=100, score=None, due=None):
    return add_grade(db, user.id, course.id, GradeCreate(
        name=name, category=category, max_score=max_score, score=score,
        due_date=due, schedule_as=GradeSchedule.TASK,
    ))


# ------------------------------------------------------------- leverage --

def test_the_item_carrying_the_most_weight_ranks_first(db, user):
    """No estimates anywhere, which is the ordinary case -- 21 of 22 real
    outstanding items have none."""
    course = course_with(db, user, {"Assignment": 20.0, "Final": 80.0})
    grade(db, user, course, "Assignment 1", "Assignment")
    grade(db, user, course, "Final exam", "Final")

    path = cheapest_path(db, user.id, course.id)

    assert [item.name for item in path.items] == ["Final exam", "Assignment 1"]
    assert path.items[0].leverage > path.items[1].leverage
    assert path.estimated_count == 0
    assert path.unestimated_count == 2


def test_the_spread_does_not_depend_on_what_the_other_items_are_assumed_to_do(db, user):
    """The claim the ranking rests on. The other outstanding items contribute
    the same amount to both halves of the subtraction, so they cancel."""
    from app.Grades.services.grade_service import project_average

    course = course_with(db, user, {"Assignment": 50.0, "Final": 50.0})
    target = grade(db, user, course, "Assignment 1", "Assignment")
    grade(db, user, course, "Assignment 2", "Assignment")
    grade(db, user, course, "Final exam", "Final")

    db.refresh(course)
    spreads = set()
    for baseline in (0.0, 0.25, 0.5):
        full = project_average(course, baseline, {target.id: 1.0})
        none = project_average(course, baseline, {target.id: 0.0})
        spreads.add(round(full - none, 2))

    assert len(spreads) == 1, f"the spread moved with the baseline: {spreads}"


def test_an_item_in_a_weightless_category_is_left_out(db, user):
    """It cannot move anything, so listing it would be offering work that
    changes nothing."""
    course = course_with(db, user, {"Assignment": 100.0, "Quiz": 0.0})
    grade(db, user, course, "Assignment 1", "Assignment")
    grade(db, user, course, "Quiz 1", "Quiz")

    path = cheapest_path(db, user.id, course.id)

    assert [item.name for item in path.items] == ["Assignment 1"]


def test_a_bonus_item_is_not_offered_as_a_route_to_the_target(db, user):
    """Bonus adds on top rather than composing the average, so chasing it is
    how you spend a weekend moving a number that was never going to reach."""
    course = course_with(db, user, {"Assignment": 100.0, "Bonus": 5.0})
    grade(db, user, course, "Assignment 1", "Assignment")
    grade(db, user, course, "Bonus lab", "Bonus")

    path = cheapest_path(db, user.id, course.id)

    assert [item.name for item in path.items] == ["Assignment 1"]


def test_a_marked_item_is_not_still_outstanding(db, user):
    course = course_with(db, user, {"Assignment": 100.0})
    grade(db, user, course, "Assignment 1", "Assignment", score=80)
    grade(db, user, course, "Assignment 2", "Assignment")

    path = cheapest_path(db, user.id, course.id)

    assert [item.name for item in path.items] == ["Assignment 2"]


# -------------------------------------------------------------- the hours --

def estimate(db, grade_row, minutes):
    """Put an estimate on the task the grade raised, as the student would."""
    task = db.query(TaskModel).filter(TaskModel.grade_id == grade_row.id).first()
    task.estimated_minutes = minutes
    db.commit()
    return task


def test_an_estimate_turns_leverage_into_a_rate(db, user):
    course = course_with(db, user, {"Assignment": 100.0})
    one = grade(db, user, course, "Assignment 1", "Assignment", due=datetime.date(2026, 10, 1))
    estimate(db, one, 120)

    path = cheapest_path(db, user.id, course.id)

    assert path.items[0].estimated_minutes == 120
    assert path.items[0].per_hour == round(path.items[0].leverage / 2, 2)


def test_the_best_rate_is_named_rather_than_put_at_the_top(db, user):
    """The cheap item that pays best per hour is worth saying, but it is not
    the heaviest thing left and the list must not claim it is."""
    course = course_with(db, user, {"Assignment": 30.0, "Final": 70.0})
    quick = grade(db, user, course, "Assignment 1", "Assignment",
                  due=datetime.date(2026, 10, 1))
    slow = grade(db, user, course, "Final exam", "Final", due=datetime.date(2026, 12, 1))
    estimate(db, quick, 60)      # 30 points of average in an hour
    estimate(db, slow, 60 * 20)  # 70 points across twenty

    path = cheapest_path(db, user.id, course.id)

    assert [item.name for item in path.items] == ["Final exam", "Assignment 1"]
    assert path.best_value_grade_id == quick.id


def test_one_estimate_does_not_drag_a_small_item_to_the_top(db, user):
    """The bug that only showed up against real courses: a single estimated lab
    worth four points outranked an unestimated final worth forty-five, because
    carrying an estimate was being read as evidence of being worth doing."""
    course = course_with(db, user, {"Assignment": 10.0, "Final": 90.0})
    small = grade(db, user, course, "Assignment 1", "Assignment",
                  due=datetime.date(2026, 10, 1))
    estimate(db, small, 60)
    grade(db, user, course, "Final exam", "Final")

    path = cheapest_path(db, user.id, course.id)

    assert [item.name for item in path.items] == ["Final exam", "Assignment 1"]
    assert (path.estimated_count, path.unestimated_count) == (1, 1)


def test_a_lone_estimate_names_no_best_value(db, user):
    """There is nothing to compare it against, and "best of one" is noise
    dressed as a finding."""
    course = course_with(db, user, {"Assignment": 50.0, "Final": 50.0})
    one = grade(db, user, course, "Assignment 1", "Assignment",
                due=datetime.date(2026, 10, 1))
    estimate(db, one, 60)
    grade(db, user, course, "Final exam", "Final")

    assert cheapest_path(db, user.id, course.id).best_value_grade_id is None


# ------------------------------------------------------------ the target --

def test_an_unreachable_target_is_reported_as_such(db, user):
    """So the ranking is not read as a plan that gets you there when nothing
    can."""
    course = course_with(db, user, {"Assignment": 50.0, "Final": 50.0})
    grade(db, user, course, "Assignment 1", "Assignment", score=10)
    grade(db, user, course, "Final exam", "Final")

    path = cheapest_path(db, user.id, course.id)

    assert path.best == pytest.approx(55.0, abs=0.5)
    assert path.reachable is False


def test_a_courses_own_target_beats_the_account_default(db, user):
    course = course_with(db, user, {"Assignment": 100.0})
    course.target_grade = 60.0
    db.commit()
    grade(db, user, course, "Assignment 1", "Assignment")

    assert cheapest_path(db, user.id, course.id).target == 60.0


# --------------------------------------------------------- the silent one --

def test_ranking_leaves_nothing_pending_in_the_session(db, user):
    """The mutate-and-restore version of item_leverage passes every other test
    here, including one that re-reads every score from the database -- because
    it puts the value back before anybody looks.

    What it cannot hide is the session. Setting a mapped attribute flags the row
    as modified whether or not the value ends up where it started, so after this
    a GET is carrying a pending UPDATE that the next commit anywhere would
    flush. Worse, restoring only happens on the happy path: raise between the
    two projections and the wrong score is what persists.

    So the assertion is on `db.dirty`, not on the values. It took a mutation to
    work that out -- the obvious version of this test was green against the bug.
    """
    course = course_with(db, user, {"Assignment": 50.0, "Final": 50.0})
    grade(db, user, course, "Assignment 1", "Assignment", score=72)
    grade(db, user, course, "Final exam", "Final")
    before = {g.id: g.score for g in db.query(GradeModel).all()}

    cheapest_path(db, user.id, course.id)

    assert not db.dirty, "computing a ranking left a pending write behind"
    db.expire_all()
    assert {g.id: g.score for g in db.query(GradeModel).all()} == before


# ----------------------------------------------- what the audit turned up --

def test_estimates_are_scoped_to_the_course(db, user):
    """The filter originally named only "has a grade and has an estimate", so
    every course page load read every such task in the table. Nothing came back
    wrong -- a grade id matches one grade -- so it was a full scan whose result
    happened to be right, invisible until the table is large.
    """
    from app.Grades.services.cheapest_path import estimates_by_grade

    mine = course_with(db, user, {"Assignment": 100.0}, code="CPSC 221")
    other = course_with(db, user, {"Assignment": 100.0}, code="CPSC 210")
    here = grade(db, user, mine, "Assignment 1", "Assignment",
                 due=datetime.date(2026, 10, 1))
    there = grade(db, user, other, "Assignment 1", "Assignment",
                  due=datetime.date(2026, 10, 1))
    estimate(db, here, 60)
    estimate(db, there, 120)

    loaded = estimates_by_grade(db, mine.id)

    assert loaded == {here.id: 60}, "another course's estimates came back too"


def test_another_users_estimate_is_never_read(db, user):
    from app.Grades.services.cheapest_path import estimates_by_grade
    from conftest import make_user

    intruder = make_user(db, "someone-else@example.com")
    theirs = course_with(db, intruder, {"Assignment": 100.0}, code="ZZZZ 100")
    theirgrade = grade(db, intruder, theirs, "Assignment 1", "Assignment",
                       due=datetime.date(2026, 10, 1))
    estimate(db, theirgrade, 300)

    mine = course_with(db, user, {"Assignment": 100.0})
    grade(db, user, mine, "Assignment 1", "Assignment")

    assert estimates_by_grade(db, mine.id) == {}


def test_the_panel_reports_the_stored_average(db, user):
    """The stored column is authoritative -- every write path recomputes and
    commits it, and the course header on the same page renders that value.
    Recomputing here is how one screen ends up showing two averages for one
    course, which is the fault get_course's docstring already records.
    """
    course = course_with(db, user, {"Assignment": 50.0, "Final": 50.0})
    grade(db, user, course, "Assignment 1", "Assignment", score=72)
    grade(db, user, course, "Final exam", "Final")

    db.refresh(course)
    assert cheapest_path(db, user.id, course.id).current == round(course.average, 2)
