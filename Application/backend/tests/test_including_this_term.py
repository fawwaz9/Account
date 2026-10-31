"""The cumulative average and CGPA including this term (Phase 4 D5).

The official pair counts only courses with a final grade, so marks entered during
a term never move it. The second pair counts each current course at its running
average, the figure the Semester Average uses, with its credits. Pinned here:

* the official pair is untouched by anything this adds;
* a current course counts at exactly the Semester Average's figure, credit-weighted;
* a course with a final counts once, at the final;
* unmarked, past-without-final, future and transfer courses stay out;
* the pair is absent when it would only repeat the official one;
* the CGPA half follows the GPA-scale setting.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app.Auth.dependencies import get_current_user
from app.Grades.schemas.grade import GradeCreate
from app.Grades.services.dash_services import (
    averages_including_this_term,
    calculate_cgpa,
    calculate_cumulative_average,
    get_dashboard,
    results_including_this_term,
)
from app.Grades.services.grade_service import add_grade, calculate_gpa_points
from app.Grades.utils.terms import CURRENT, FUTURE, PAST
from app.Users.services.user_service import get_preferences
from conftest import make_course, make_user


def bucketed(course, bucket):
    """These rules receive courses with term_bucket already attached."""
    course.term_bucket = bucket
    return course


def finished(db, user, code, final, credits=3.0):
    return bucketed(make_course(db, user.id, code, final_grade=final, credits=credits), PAST)


def running(db, user, code, average, credits=3.0, bucket=CURRENT, **overrides):
    return bucketed(make_course(db, user.id, code, average=average, credits=credits, **overrides), bucket)


# ------------------------------------------------------------------ the rule --

def test_a_current_course_counts_at_its_running_average_credit_weighted(db, user):
    courses = [
        finished(db, user, "CPSC 110", 90.0, credits=3.0),
        running(db, user, "CPSC 210", 70.0, credits=6.0),
    ]

    average, cgpa = averages_including_this_term(courses, gpa_scale_enabled=True)

    # (90 * 3 + 70 * 6) / 9 = 76.666...
    assert average == 76.67
    expected = (calculate_gpa_points(90.0) * 3 + calculate_gpa_points(70.0) * 6) / 9
    assert cgpa == round(expected, 2)


def test_the_official_pair_is_untouched(db, user):
    courses = [
        finished(db, user, "CPSC 110", 90.0),
        running(db, user, "CPSC 210", 50.0),
    ]

    assert calculate_cumulative_average(courses) == 90.0
    assert calculate_cgpa(courses) == calculate_gpa_points(90.0)


def test_a_current_course_with_a_final_counts_once_at_the_final(db, user):
    course = running(db, user, "CPSC 210", 60.0, final_grade=80.0)
    other = running(db, user, "MATH 200", 70.0)

    pairs, any_running = results_including_this_term([course, other])

    assert sorted(pairs) == [(70.0, 3.0), (80.0, 3.0)]
    assert any_running


@pytest.mark.parametrize("label, make", [
    ("unmarked current course", lambda db, u: running(db, u, "X 100", 0.0)),
    ("past course without a final", lambda db, u: running(db, u, "X 100", 75.0, bucket=PAST)),
    ("future course", lambda db, u: running(db, u, "X 100", 75.0, bucket=FUTURE)),
    ("transfer credit", lambda db, u: running(db, u, "X 100", 75.0, transfer_credit=True)),
    ("course without credits", lambda db, u: running(db, u, "X 100", 75.0, credits=0.0)),
])
def test_courses_that_stay_out(db, user, label, make):
    official = finished(db, user, "CPSC 110", 90.0)
    left_out = make(db, user)

    pairs, any_running = results_including_this_term([official, left_out])

    assert pairs == [(90.0, 3.0)], label
    assert not any_running, label


def test_absent_when_it_would_repeat_the_official_pair(db, user):
    courses = [finished(db, user, "CPSC 110", 90.0), running(db, user, "CPSC 210", 0.0)]

    assert averages_including_this_term(courses, gpa_scale_enabled=True) == (None, None)


def test_the_cgpa_half_follows_the_gpa_scale_setting(db, user):
    courses = [running(db, user, "CPSC 210", 80.0)]

    average, cgpa = averages_including_this_term(courses, gpa_scale_enabled=False)

    assert average == 80.0
    assert cgpa is None


def test_a_term_with_nothing_finished_yet(db, user):
    """A first-term student: the official pair is empty, this one is not."""
    courses = [running(db, user, "CPSC 110", 80.0), running(db, user, "MATH 100", 70.0, credits=4.0)]

    assert calculate_cumulative_average(courses) == 0.0
    assert averages_including_this_term(courses, gpa_scale_enabled=False)[0] == round((240 + 280) / 7, 2)


# ------------------------------------------------- through the real dashboard --

def mark(db, user, course, category, got):
    """Through the service, so the stored average is the one marks really make."""
    add_grade(db, user.id, course.id, GradeCreate(name=f"{category} {uuid.uuid4().hex[:4]}",
                                                  category=category, score=got, max_score=100.0))


@pytest.fixture
def term(db, user):
    """Third year, Fall: one finished course, two current, one marked."""
    user.current_school_year = 3
    user.current_semester = "Fall"
    db.commit()
    make_course(db, user.id, "CPSC 110", year=2, semester="Fall", final_grade=88.0, credits=4.0)
    marked = make_course(db, user.id, "CPSC 310", year=3, semester="Fall", credits=4.0)
    make_course(db, user.id, "CPSC 320", year=3, semester="Fall", credits=3.0)
    mark(db, user, marked, "Assignment", 72.0)
    return marked


def test_the_dashboard_counts_the_semester_average_figure(db, user, term):
    dashboard = get_dashboard(db, user.id)

    # The one marked current course is the Semester Average; the unmarked one is skipped.
    assert dashboard.semester_average == 72.0
    assert dashboard.cumulative_average == 88.0
    assert dashboard.cumulative_average_including_term == round((88.0 * 4 + 72.0 * 4) / 8, 2)


def test_the_dashboard_cgpa_half_follows_the_setting(db, user, term):
    scale_on = get_preferences(user).gpa_scale_enabled
    dashboard = get_dashboard(db, user.id)

    if scale_on:
        expected = (calculate_gpa_points(88.0) * 4 + calculate_gpa_points(72.0) * 4) / 8
        assert dashboard.cgpa_including_term == round(expected, 2)
    else:
        assert dashboard.cgpa_including_term is None


def test_a_mark_entered_this_term_moves_the_new_pair_and_not_the_official_one(db, user, term):
    before = get_dashboard(db, user.id)
    mark(db, user, term, "Assignment", 100.0)
    db.expire_all()
    after = get_dashboard(db, user.id)

    assert after.cumulative_average == before.cumulative_average
    assert after.cumulative_average_including_term > before.cumulative_average_including_term


@pytest.fixture
def client(db, user):
    app.main.app.dependency_overrides[get_current_user] = lambda: user
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_route_carries_both_fields(db, user, term, client):
    body = client.get(f"/api/grades/{user.id}/grades/dashboard").json()

    assert body["cumulative_average_including_term"] == 80.0
    assert "cgpa_including_term" in body


def test_the_route_reads_only_the_caller_s_courses(db, user, term, client):
    """Another user's marked current course never reaches the caller's figure."""
    other = make_user(db, "someone-else@example.com")
    other.current_school_year = 3
    other.current_semester = "Fall"
    db.commit()
    theirs = make_course(db, other.id, "CPSC 310", year=3, semester="Fall", credits=40.0)
    mark(db, other, theirs, "Assignment", 10.0)

    body = client.get(f"/api/grades/{user.id}/grades/dashboard").json()

    assert body["cumulative_average_including_term"] == 80.0
