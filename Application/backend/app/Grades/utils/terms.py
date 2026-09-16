"""Placing a course in time, relative to the term the student is in now.

Courses carry a school year (1-10) and a semester, but nothing on them says
whether that term has happened yet. That comparison lives here so the grades
page, the dashboard rollup, and the course payload all agree on it.
"""

from datetime import date

from app.Grades.utils.enums import SEMESTER_ORDER

PAST = "past"
CURRENT = "current"
FUTURE = "future"


#: When each term runs, and which calendar year it lands in.
#:
#: The third element is the offset from the school year's own calendar year, and
#: it is the part to get right: a school year written "2025-2026" starts in the
#: autumn of the first and finishes in the summer of the second. Fall takes the
#: year the school year began; everything after New Year takes the next one.
#: Zero there would put Winter eight months *before* the Fall it follows.
#:
#: A constant for now. When terms become editable this is the seam -- one table
#: read through one accessor, rather than dates spread across the services.
TERM_DATES: dict[str, tuple[tuple[int, int], tuple[int, int], int]] = {
    "Fall": ((9, 1), (12, 31), 0),
    "Winter": ((1, 1), (4, 30), 1),
    "Spring": ((5, 1), (6, 30), 1),
    "Summer": ((7, 1), (8, 31), 1),
}


def calendar_year_of(school_year: int | None, first_year: int | None) -> int | None:
    """Which calendar year a school year's Fall began in.

    School year 1 began in `first_year`, so year N began N-1 years later. Both
    None-tolerant because the anchor is a setting a student may not have filled
    in, and the honest answer then is "unknown" rather than a guess.
    """
    if school_year is None or first_year is None:
        return None
    return first_year + school_year - 1


def suggest_first_year(courses) -> int | None:
    """What the anchor probably is, worked out from courses that carry dates.

    Evidence rather than a label. The obvious source is `term_label` -- it
    already reads "2025-2026" -- but nothing keeps it current: the real account
    carries that string while its year-3 Fall courses run September **2026**,
    so trusting it would set the anchor a year out and silently mis-date every
    term in the app. A course's own start date is a fact somebody entered about
    a real class.

    Inverts the arithmetic in `term_dates`: a term starting in calendar year Y
    means school year 1 began at Y - offset - (school_year - 1).

    Takes the most common answer, so one mistyped course cannot outvote the
    rest, and returns None when nothing is dated.
    """
    votes: dict[int, int] = {}
    for course in courses:
        entry = TERM_DATES.get(course.semester or "")
        if entry is None or course.start_date is None or course.year is None:
            continue
        _, _, offset = entry
        first_year = course.start_date.year - offset - course.year + 1
        votes[first_year] = votes.get(first_year, 0) + 1

    if not votes:
        return None
    return max(votes, key=lambda year: (votes[year], -year))


def term_dates(
    semester: str | None,
    school_year: int | None,
    first_year: int | None,
) -> tuple[date, date] | None:
    """The real dates a term runs, or None when they cannot be known.

    None rather than a default, in every failing case: no anchor set, an
    unrecognised semester, a missing school year. Anything that reads this has
    to say it does not know, because a term silently dated to year 1 would put
    a current course three years in the past and nothing on screen would
    explain why.
    """
    entry = TERM_DATES.get(semester or "")
    if entry is None:
        return None

    began = calendar_year_of(school_year, first_year)
    if began is None:
        return None

    (start_month, start_day), (end_month, end_day), offset = entry
    return (
        date(began + offset, start_month, start_day),
        date(began + offset, end_month, end_day),
    )


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
