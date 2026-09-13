"""Placing a course in time, relative to the term the student is in now.

Courses carry a school year (1-10) and a semester, but nothing on them says
whether that term has happened yet. That comparison lives here so the grades
page, the dashboard rollup, and the course payload all agree on it.
"""

from app.Grades.utils.enums import SEMESTER_ORDER

PAST = "past"
CURRENT = "current"
FUTURE = "future"


def term_key(school_year: int | None, semester: str | None) -> tuple[int, int]:
    """Order terms as (school year, position within that year)."""
    return (school_year or 0, SEMESTER_ORDER.get(semester or "", 0))


def term_bucket(course, current_school_year: int | None, current_semester: str | None) -> str:
    """Sort one course into past, current, or future.

    With no academic status set everything reads as current, so a student who
    has not filled the setting in still sees their courses rather than an empty
    page.
    """
    if current_school_year is None or current_semester is None:
        return CURRENT

    course_key = term_key(course.year, course.semester)
    now_key = term_key(current_school_year, current_semester)

    if course_key < now_key:
        return PAST
    if course_key > now_key:
        return FUTURE
    return CURRENT


def effective_target(course, default_target: float) -> float:
    """The course's own target, or the account default when it has none.

    Here rather than in a service because two callers now need it and one of
    them is Tasks: importing it from dash_services closed a loop through
    grade_service and grade_schedule back into task_service. This module is
    pure -- courses in, answers out, no session -- so anything may read it.
    """
    return course.target_grade if course.target_grade is not None else default_target


def course_result_grade(course, average: float | None = None) -> float | None:
    """The single grade a finished course should be represented by.

    Prefers the final grade the professor submitted, falls back to the running
    average, and returns None when the course has neither. A past course that
    was never filled in must not drag its year's average toward zero.

    `average` overrides the stored column for a caller that has just recomputed
    it. It exists so such a caller does not have to assign the fresh value onto
    the mapped attribute to be seen -- a read that writes to a mapped column is
    one stray commit away from a GET that changes data.
    """
    if course.final_grade and course.final_grade > 0:
        return course.final_grade

    running = course.average if average is None else average
    if running and running > 0:
        return running
    return None


def year_average(courses) -> float | None:
    """Average across a year's courses, skipping ones with nothing recorded."""
    grades = [
        grade
        for grade in (course_result_grade(course) for course in courses)
        if grade is not None
    ]
    if not grades:
        return None

    return round(sum(grades) / len(grades), 2)
