"""Quick capture: one line in, one real task out.

The tokenizer is tested separately and without a database. What is worth
testing here is the half that needs one -- matching a typed code against courses
that actually exist, and what happens when it matches nothing.
"""
from datetime import date

import pytest

from app._database.models import TaskModel
from app.Grades.services.course_lookup import resolve_course
from app.Tasks.services.quick_capture_service import build_preview, capture
from conftest import make_course, make_user


def courses(db, user):
    """The shapes this account really uses, suffixed campus codes included."""
    return [
        make_course(db, user.id, "COSC 121"),
        make_course(db, user.id, "CPSC_V 210"),
        make_course(db, user.id, "MATH 100"),
    ]


# --------------------------------------------------------- matching a code --

def test_an_exact_code_matches(db, user):
    courses(db, user)
    assert resolve_course(db, user.id, "COSC 121").code == "COSC 121"


def test_case_and_spacing_do_not_matter(db, user):
    courses(db, user)
    for typed in ("cosc121", "COSC121", "cosc 121", "CoSc  121"):
        assert resolve_course(db, user.id, typed).code == "COSC 121"


def test_a_campus_suffix_does_not_have_to_be_typed(db, user):
    """"cpsc 210" finds "CPSC_V 210" without hardcoding what _V means."""
    courses(db, user)
    assert resolve_course(db, user.id, "cpsc 210").code == "CPSC_V 210"


def test_an_underscore_need_not_be_typed(db, user):
    """"statv201" and "stat201" both find "STAT_V 201"."""
    make_course(db, user.id, "STAT_V 201")

    assert resolve_course(db, user.id, "statv201").code == "STAT_V 201"
    assert resolve_course(db, user.id, "stat201").code == "STAT_V 201"
    assert resolve_course(db, user.id, "STAT_V 201").code == "STAT_V 201"


def test_a_code_matching_nothing_resolves_to_nothing(db, user):
    courses(db, user)
    assert resolve_course(db, user.id, "CS 221") is None


def test_the_number_has_to_match(db, user):
    courses(db, user)
    assert resolve_course(db, user.id, "COSC 999") is None


def test_an_ambiguous_prefix_resolves_to_nothing(db, user):
    """Filing a lab against the wrong course is worse than against none."""
    make_course(db, user.id, "CPSC_V 210")
    make_course(db, user.id, "CPSCX 210")

    assert resolve_course(db, user.id, "cpsc 210") is None


def test_another_users_course_is_never_matched(db, user):
    stranger = make_user(db, "stranger@example.com")
    make_course(db, stranger.id, "COSC 121")

    assert resolve_course(db, user.id, "COSC 121") is None


# ----------------------------------------------------------------- preview --

def test_the_motivating_line(db, user):
    courses(db, user)
    preview = build_preview(db, user.id, "cosc121 lab due fri")

    assert preview.course_code == "COSC 121"
    assert preview.title == "lab"
    assert preview.due_date is not None
    assert preview.can_create is True


def test_an_unmatched_code_stays_in_the_title(db, user):
    """Never swallow text that was not used -- the student has to see it."""
    courses(db, user)
    preview = build_preview(db, user.id, "CS221 lab due fri")

    assert preview.course_id is None
    assert preview.unmatched_course == "CS 221"
    assert "CS 221" in preview.title
    assert preview.can_create is True


def test_a_plain_line_is_just_a_title(db, user):
    preview = build_preview(db, user.id, "buy milk")

    assert preview.title == "buy milk"
    assert preview.matched == []
    assert preview.can_create is True


def test_a_line_with_nothing_left_cannot_create(db, user):
    """"fri" alone parses a date and leaves no task to make."""
    preview = build_preview(db, user.id, "fri")

    assert preview.title == ""
    assert preview.can_create is False


def test_an_absurd_duration_is_dropped_rather_than_failing_the_line(db, user):
    preview = build_preview(db, user.id, "readings 9000m")

    assert preview.estimated_minutes is None
    assert preview.can_create is True


def test_a_duration_is_carried_through(db, user):
    preview = build_preview(db, user.id, "readings 90m")

    assert preview.estimated_minutes == 90


# ----------------------------------------------------------------- capture --

def test_capture_creates_the_task_the_preview_described(db, user):
    courses(db, user)
    task, preview = capture(db, user.id, "cosc121 lab report due fri 2h")

    assert task.title == preview.title == "lab report"
    assert task.course_code == "COSC 121"
    assert task.estimated_minutes == 120
    assert task.due_date == preview.due_date
    assert db.query(TaskModel).count() == 1


def test_a_captured_task_is_an_ordinary_task(db, user):
    """Nothing about it is special afterwards -- it edits and ticks off normally."""
    task, _ = capture(db, user.id, "buy milk")

    assert task.done is False
    assert task.grade_id is None
    assert task.recurring_id is None


def test_capturing_nothing_is_refused(db, user):
    with pytest.raises(ValueError, match="nothing here"):
        capture(db, user.id, "fri")

    assert db.query(TaskModel).count() == 0


def test_preview_writes_nothing(db, user):
    build_preview(db, user.id, "cosc121 lab due fri")

    assert db.query(TaskModel).count() == 0
