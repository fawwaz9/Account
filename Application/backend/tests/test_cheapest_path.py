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


def test_the_best_rate_leads_even_when_it_is_not_the_heaviest(db, user):
    """Rate is the ranking now, so the cheap item that pays best per hour goes
    first -- above an item carrying more than twice the points."""
    course = course_with(db, user, {"Assignment": 30.0, "Final": 70.0})
    quick = grade(db, user, course, "Assignment 1", "Assignment",
                  due=datetime.date(2026, 10, 1))
    slow = grade(db, user, course, "Final exam", "Final", due=datetime.date(2026, 12, 1))
    estimate(db, quick, 60)      # 30 points of average in an hour
    estimate(db, slow, 60 * 20)  # 70 points across twenty

    path = cheapest_path(db, user.id, course.id)

    assert [item.name for item in path.items] == ["Assignment 1", "Final exam"]
    assert path.items[0].per_hour > path.items[1].per_hour
    assert path.items[0].leverage < path.items[1].leverage, "and it is the smaller item"


def test_a_lone_estimate_takes_the_top_spot_from_a_heavier_item(db, user):
    """Asked for deliberately, and the cost of it recorded here rather than
    discovered again.

    Ranking on rate means an item with an estimate outranks every item without
    one, because nothing unrated has a rate to beat it. A lab worth ten points
    therefore sits above a final worth ninety. That is the rule working, not
    failing -- but with one estimate across twenty-three real outstanding items
    it is the ordinary case, so the panel's prompt to add estimates is load
    bearing and not a nicety.
    """
    course = course_with(db, user, {"Assignment": 10.0, "Final": 90.0})
    small = grade(db, user, course, "Assignment 1", "Assignment",
                  due=datetime.date(2026, 10, 1))
    estimate(db, small, 60)
    grade(db, user, course, "Final exam", "Final")

    path = cheapest_path(db, user.id, course.id)

    assert [item.name for item in path.items] == ["Assignment 1", "Final exam"]
    assert path.items[0].leverage < path.items[1].leverage
    assert (path.estimated_count, path.unestimated_count) == (1, 1)


def test_an_unrated_item_never_outranks_a_rated_one(db, user):
    """The half of the rule that has no number behind it. An item with no
    estimate has no rate, and it is not given one -- zero would bury it,
    infinity would crown it. It sorts below every rated item instead.
    """
    course = course_with(db, user, {"Assignment": 50.0, "Final": 50.0})
    one = grade(db, user, course, "Assignment 1", "Assignment",
                due=datetime.date(2026, 10, 1))
    # Twenty hours for fifty points: a dreadful rate, and still ahead of an
    # item with no rate at all.
    estimate(db, one, 60 * 20)
    grade(db, user, course, "Final exam", "Final")

    path = cheapest_path(db, user.id, course.id)

    assert [item.name for item in path.items] == ["Assignment 1", "Final exam"]
    assert path.items[0].per_hour is not None
    assert path.items[1].per_hour is None


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


# ------------------------------------------------------------ the top three --

def test_only_three_items_are_ever_returned(db, user):
    """"At all times" -- a course with eight things left shows three."""
    course = course_with(db, user, {"Assignment": 100.0})
    for n in range(1, 9):
        grade(db, user, course, f"Assignment {n}", "Assignment")

    path = cheapest_path(db, user.id, course.id)

    assert len(path.items) == 3
    assert path.remaining_count == 8, "and it still says how many there were"


def test_the_cut_happens_after_the_ranking(db, user):
    """The failure this guards is "top three" quietly meaning "first three
    found". The heaviest item is created last here, so a cut taken before the
    sort would drop precisely the one that should lead.
    """
    course = course_with(db, user, {"Quiz": 5.0, "Assignment": 15.0, "Final": 80.0})
    grade(db, user, course, "Quiz 1", "Quiz")
    grade(db, user, course, "Quiz 2", "Quiz")
    grade(db, user, course, "Quiz 3", "Quiz")
    grade(db, user, course, "Assignment 1", "Assignment")
    grade(db, user, course, "Final exam", "Final")

    path = cheapest_path(db, user.id, course.id)

    assert path.items[0].name == "Final exam"
    assert [item.name for item in path.items] == \
        ["Final exam", "Assignment 1", "Quiz 1"]


def test_points_break_a_tie_between_equal_rates(db, user):
    """The "then by pts" half of the rule.

    The weights are 25/75 so the two leverages come out exact -- at 30/60 they
    normalise to 33.33 and 66.67 and the "equal" rates differ in the second
    decimal, which makes the tie a rounding artifact and tests nothing.

    The names are chosen so the last-resort alphabetical fallback would answer
    "Assignment 1". Only points give "Final exam", so a pass here is the
    tiebreak working rather than the sort merely being stable.
    """
    course = course_with(db, user, {"Assignment": 25.0, "Final": 75.0})
    small = grade(db, user, course, "Assignment 1", "Assignment",
                  due=datetime.date(2026, 10, 1))
    big = grade(db, user, course, "Final exam", "Final", due=datetime.date(2026, 12, 1))
    estimate(db, small, 60)       # 25 points in an hour
    estimate(db, big, 180)        # 75 points in three -- the same rate

    path = cheapest_path(db, user.id, course.id)

    assert path.items[0].per_hour == path.items[1].per_hour, "the rates must tie"
    assert [item.name for item in path.items] == ["Final exam", "Assignment 1"]


def test_the_counts_describe_the_three_on_screen(db, user):
    """They feed a line that says "these" next to three visible rows, so a
    count taken over everything outstanding would describe items nobody can
    see -- "5 of these carry no estimate" beside three of them."""
    course = course_with(db, user, {"Assignment": 100.0})
    for n in range(1, 7):
        grade(db, user, course, f"Assignment {n}", "Assignment")

    path = cheapest_path(db, user.id, course.id)

    assert path.estimated_count + path.unestimated_count == len(path.items) == 3
    assert path.remaining_count == 6
