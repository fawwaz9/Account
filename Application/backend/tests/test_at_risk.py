"""Tasks from courses you are behind on, and where they sort.

Risk leads the existing date ordering rather than replacing it: the page groups
by how soon, and that grouping is the thing it exists to show.
"""
import datetime
import uuid

import pytest

from app._database.models import TaskModel
from app.Tasks.services.task_service import list_tasks, risk_band
from tests.conftest import make_course


@pytest.fixture
def current_term(db, user):
    """A student whose current term is Fall of year 3, matching make_course."""
    user.current_school_year = 3
    user.current_semester = "Fall"
    user.preferences = {"default_target_grade": 85.0}
    db.commit()
    return user


def add_task(db, user, title, *, course_id=None, due_date=None):
    task = TaskModel(
        id=uuid.uuid4(), user_id=user.id, title=title, course_id=course_id,
        due_date=due_date, done=False, archived=False, tags=[],
    )
    db.add(task)
    db.commit()
    return task


def titles(tasks):
    return [task.title for task in tasks]


def test_a_course_below_target_badges_its_tasks(db, current_term):
    course = make_course(db, current_term.id, "COSC 111", average=70.0)
    add_task(db, current_term, "Lab 4", course_id=course.id)

    tasks = list_tasks(db, current_term.id)

    assert tasks[0].risk == "severe", "15 points below an 85 target"


def test_a_course_on_target_badges_nothing(db, current_term):
    course = make_course(db, current_term.id, "COSC 111", average=90.0)
    add_task(db, current_term, "Lab 4", course_id=course.id)

    assert list_tasks(db, current_term.id)[0].risk is None


def test_a_task_with_no_course_badges_nothing(db, current_term):
    add_task(db, current_term, "Renew bus pass")

    assert list_tasks(db, current_term.id)[0].risk is None


def test_a_past_course_below_target_does_not_badge(db, current_term):
    """History, not something tonight's work can move -- the dashboard's rule."""
    course = make_course(db, current_term.id, "HIST 100", year=1, average=50.0)
    add_task(db, current_term, "Old essay", course_id=course.id)

    assert list_tasks(db, current_term.id)[0].risk is None


def test_a_course_with_nothing_recorded_does_not_badge(db, current_term):
    course = make_course(db, current_term.id, "COSC 111", average=0.0)
    add_task(db, current_term, "Lab 4", course_id=course.id)

    assert list_tasks(db, current_term.id)[0].risk is None


def test_a_courses_own_target_beats_the_account_default(db, current_term):
    """Default is 85. A course aiming at 70 is not behind at 75."""
    course = make_course(db, current_term.id, "COSC 111", average=75.0, target_grade=70.0)
    add_task(db, current_term, "Lab 4", course_id=course.id)

    assert list_tasks(db, current_term.id)[0].risk is None


def test_the_account_default_applies_when_a_course_has_no_target(db, current_term):
    course = make_course(db, current_term.id, "COSC 111", average=75.0, target_grade=None)
    add_task(db, current_term, "Lab 4", course_id=course.id)

    assert list_tasks(db, current_term.id)[0].risk == "moderate"


def test_risk_leads_but_dates_still_order_within_a_band(db, current_term):
    behind = make_course(db, current_term.id, "COSC 111", average=70.0)
    fine = make_course(db, current_term.id, "MATH 200", average=90.0)
    day = datetime.date(2026, 9, 20)

    # Deliberately added in the wrong order for both keys.
    add_task(db, current_term, "Fine, sooner", course_id=fine.id, due_date=day)
    add_task(db, current_term, "Risky, later", course_id=behind.id,
             due_date=day + datetime.timedelta(days=5))
    add_task(db, current_term, "Risky, sooner", course_id=behind.id, due_date=day)

    assert titles(list_tasks(db, current_term.id)) == [
        "Risky, sooner", "Risky, later", "Fine, sooner",
    ]


def test_worse_courses_sort_above_less_bad_ones(db, current_term):
    severe = make_course(db, current_term.id, "COSC 111", average=60.0)   # 25 below
    moderate = make_course(db, current_term.id, "MATH 200", average=78.0)  # 7 below
    mild = make_course(db, current_term.id, "PHYS 102", average=82.0)      # 3 below
    day = datetime.date(2026, 9, 20)

    add_task(db, current_term, "Mild", course_id=mild.id, due_date=day)
    add_task(db, current_term, "Severe", course_id=severe.id, due_date=day)
    add_task(db, current_term, "Moderate", course_id=moderate.id, due_date=day)

    assert titles(list_tasks(db, current_term.id)) == ["Severe", "Moderate", "Mild"]


def test_undated_tasks_still_sort_last_within_their_band(db, current_term):
    behind = make_course(db, current_term.id, "COSC 111", average=70.0)

    add_task(db, current_term, "Risky, undated", course_id=behind.id)
    add_task(db, current_term, "Risky, dated", course_id=behind.id,
             due_date=datetime.date(2026, 9, 20))

    assert titles(list_tasks(db, current_term.id)) == ["Risky, dated", "Risky, undated"]


@pytest.mark.parametrize("gap,band", [
    (0.1, "mild"), (5.0, "mild"), (5.1, "moderate"),
    (10.0, "moderate"), (10.1, "severe"), (40.0, "severe"),
])
def test_band_boundaries(gap, band):
    assert risk_band(gap) == band


def test_a_final_grade_is_preferred_over_the_running_average(db, current_term):
    """course_result_grade's rule, which risk has to agree with."""
    course = make_course(db, current_term.id, "COSC 111", average=60.0, final_grade=90.0)
    add_task(db, current_term, "Lab 4", course_id=course.id)

    assert list_tasks(db, current_term.id)[0].risk is None
