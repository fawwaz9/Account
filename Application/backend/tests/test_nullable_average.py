"""An unmarked course has no average, and says so.

Zero is a real grade. "Nothing marked yet" is not, and reporting the second as
the first makes a course you have not started read as one you are failing --
the same reason the cumulative average was made nullable before it.
"""
import uuid

from app._database.models import GradeModel
from app.Grades.schemas.course import Course
from app.Grades.schemas.grade import GradeCreate
from app.Grades.services.course_service import (
    course_has_marks,
    courses_with_marks,
    get_all_courses,
    get_course,
)
from app.Grades.services.dash_services import get_dashboard
from app.Grades.services.grade_service import add_grade
from conftest import make_course


def mark(db, user, course, score, excluded=False):
    return add_grade(db, user.id, course.id, GradeCreate(
        name="A1", score=score, max_score=100.0, category="Assignment", excluded=excluded,
    ))


def test_a_course_with_nothing_marked_reports_no_average(db, user):
    make_course(db, user.id, "COSC 111")

    [course] = get_all_courses(db, user.id)

    assert Course.model_validate(course).average is None


def test_a_course_with_a_mark_reports_it(db, user):
    course = make_course(db, user.id, "COSC 111", category_weights={"Assignment": 100.0})
    mark(db, user, course, 80.0)

    [listed] = get_all_courses(db, user.id)

    assert Course.model_validate(listed).average == 80.0


def test_a_course_that_genuinely_averages_zero_is_not_null(db, user):
    """The distinction the whole change exists to make."""
    course = make_course(db, user.id, "COSC 111", category_weights={"Assignment": 100.0})
    mark(db, user, course, 0.0)

    [listed] = get_all_courses(db, user.id)

    assert Course.model_validate(listed).average == 0.0


def test_a_dropped_mark_does_not_count_as_marked_work(db, user):
    """It is on the course to be seen, not to be scored.

    Written straight to GradeModel, the way every other dropped-mark test in
    this suite does it: `add_grade` builds its row field by field and does not
    carry `excluded` through, so creating one through the service would quietly
    produce a grade that counts.
    """
    course = make_course(db, user.id, "COSC 111", category_weights={"Assignment": 100.0})
    db.add(GradeModel(
        id=uuid.uuid4(), course_id=course.id, name="Dropped quiz", category="Assignment",
        score=90.0, max_score=100.0, weight=0.0, excluded=True,
    ))
    db.commit()

    assert course_has_marks(db, course.id) is False


def test_an_unmarked_item_does_not_count_either(db, user):
    course = make_course(db, user.id, "COSC 111", category_weights={"Assignment": 100.0})
    add_grade(db, user.id, course.id, GradeCreate(
        name="Not marked", score=None, max_score=100.0, category="Assignment",
    ))

    assert course_has_marks(db, course.id) is False


def test_the_single_course_read_agrees_with_the_list(db, user):
    make_course(db, user.id, "COSC 111")
    course = get_course(db, user.id, get_all_courses(db, user.id)[0].id)

    assert Course.model_validate(course).average is None


def test_courses_with_marks_finds_only_the_marked_ones(db, user):
    marked = make_course(db, user.id, "AAAA 100", category_weights={"Assignment": 100.0})
    make_course(db, user.id, "BBBB 100")
    mark(db, user, marked, 70.0)

    assert courses_with_marks(db, user.id) == {marked.id}


def test_an_unmarked_course_is_not_the_weakest_course(db, user):
    """The latent bug the null exposed: 0.0 made an unstarted course the worst."""
    good = make_course(db, user.id, "AAAA 100", category_weights={"Assignment": 100.0})
    make_course(db, user.id, "BBBB 100")  # nothing marked
    mark(db, user, good, 75.0)

    dashboard = get_dashboard(db, user.id)

    assert dashboard.weakest_course is not None
    assert dashboard.weakest_course.course_code == "AAAA 100"
    assert dashboard.best_course.course_code == "AAAA 100"


def test_a_dashboard_where_nothing_is_marked_has_no_best_or_weakest(db, user):
    make_course(db, user.id, "AAAA 100")
    make_course(db, user.id, "BBBB 100")

    dashboard = get_dashboard(db, user.id)

    assert dashboard.best_course is None
    assert dashboard.weakest_course is None


def test_the_stored_column_is_never_written_by_a_read(db, user):
    """Reporting null must not mean assigning null onto the mapped column."""
    course = make_course(db, user.id, "COSC 111")

    listed = get_all_courses(db, user.id)[0]

    assert listed.reported_average is None
    assert listed.average == 0.0
