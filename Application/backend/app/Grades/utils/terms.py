"""Placing courses in time: term dates, term order and the past/current/future bucket.

Courses carry a school year (1-10) and a term but no dates; with the user's
first-year anchor, `TERM_DATES` gives each term real dates. Also the shared answers
for a course's target and result grade, here in utils so Grades and Tasks can both
import them without a cycle.
"""

from datetime import date

from app.Grades.utils.enums import SEMESTER_ORDER

PAST = "past"
"""Term bucket of a course before the student's current term."""
CURRENT = "current"
"""Term bucket of a course in the student's current term."""
FUTURE = "future"
"""Term bucket of a course after the student's current term."""


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
    """Return the calendar year in which a school year's Fall began.

    Args:
        school_year: School year, 1 for first year; None when unknown.
        first_year: The first-year anchor; None when unset.

    Returns:
        `first_year + school_year - 1`, or None when either is missing.
    """
    if school_year is None or first_year is None:
        return None
    return first_year + school_year - 1


def suggest_first_year(courses) -> int | None:
    """Return the most likely first-year anchor, inferred from courses with start dates.

    Each dated course votes for the anchor its start date implies; the most common
    answer wins and ties go to the earlier year, so one mistyped course cannot outvote
    the rest. `term_label` is never trusted for this.

    Args:
        courses: Course rows; undated ones and unknown terms are ignored.

    Returns:
        The suggested calendar year, or None when no course is dated.
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
    """Return the first and last day of a term, or None when they cannot be known.

    Args:
        semester: "Fall", "Winter", "Spring" or "Summer".
        school_year: School year the term belongs to.
        first_year: The first-year anchor.

    Returns:
        (start, end) dates, both inclusive; None for an unknown semester, a missing
        school year or an unset anchor, never a guess.
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
    """Return a sortable (school year, position in the year) key for a term.

    Missing values sort as 0.

    Args:
        school_year: Year of study; None sorts first.
        semester: "Fall", "Winter", "Spring" or "Summer"; None or unknown sorts first.

    Returns:
        A tuple that sorts terms chronologically.
    """
    return (school_year or 0, SEMESTER_ORDER.get(semester or "", 0))


def term_bucket(course, current_school_year: int | None, current_semester: str | None) -> str:
    """Return whether a course is in the past, current or future term for the student.

    Args:
        course: Course row; its `year` and `semester` are compared.
        current_school_year: The student's school year now.
        current_semester: The student's term now.

    Returns:
        `PAST`, `CURRENT` or `FUTURE`; every course is `CURRENT` when the student's
        academic status is unset.
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
    """Return a course's target grade, or the account default when it has none.

    Args:
        course: Course row.
        default_target: The account-wide default target percentage.

    Returns:
        The target percentage to measure the course against.
    """
    return course.target_grade if course.target_grade is not None else default_target


def course_result_grade(course, average: float | None = None) -> float | None:
    """Return the single grade a course is represented by: the final, else the average.

    Args:
        course: Course row.
        average: A just-recomputed average to use instead of the stored column, so a
            caller never has to write a fresh value onto the mapped attribute.

    Returns:
        The final grade if one above 0 is recorded, else the running average if above
        0, else None, so an unfilled course never counts as zero.
    """
    if course.final_grade and course.final_grade > 0:
        return course.final_grade

    running = course.average if average is None else average
    if running and running > 0:
        return running
    return None


def year_average(courses) -> float | None:
    """Return the plain mean of a year's course grades, skipping courses with none.

    Args:
        courses: The year's course rows.

    Returns:
        The unweighted mean of `course_result_grade`, rounded to 2 places; None when
        no course has a grade.
    """
    grades = [
        grade
        for grade in (course_result_grade(course) for course in courses)
        if grade is not None
    ]
    if not grades:
        return None

    return round(sum(grades) / len(grades), 2)
