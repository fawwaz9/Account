"""Grade enumerations and their rules: terms, categories, scheduling and priority.

Pure values and functions with no session, shared by Grades, Tasks, Calendar and
Intake.
"""

from enum import Enum

class Semester(str, Enum):
    """A term of the school year, as stored in `courses.semester`.

    Declared out of calendar order; compare terms with `SEMESTER_ORDER`.
    """
    FALL = "Fall"
    WINTER = "Winter"
    SUMMER = "Summer"
    SPRING = "Spring"


# Declaration order above is not chronological, so term comparison needs this.
# A school year runs Fall (Sep-Dec) -> Winter (Jan-Apr) -> Spring -> Summer.
SEMESTER_ORDER: dict[str, int] = {
    Semester.FALL.value: 0,
    Semester.WINTER.value: 1,
    Semester.SPRING.value: 2,
    Semester.SUMMER.value: 3,
}

class GradeCategory(str, Enum):
    """The category of a piece of assessed work, as stored in `grades.category`.

    Every category but `BONUS` composes the course's 100%; see `ADDITIVE_CATEGORIES`.
    """
    ASSIGNMENT = "Assignment"
    LAB = "Lab"
    QUIZ = "Quiz"
    MIDTERM = "Midterm"
    FINAL = "Final"
    PARTICIPATION = "Participation"
    PROJECT = "Project"
    OTHER = "Other"
    #: Marks that add on top of the course rather than forming part of it. See
    #: ADDITIVE_CATEGORIES below for what that means arithmetically.
    BONUS = "Bonus"


#: Categories whose weight sits *outside* the 100% a course is marked out of.
#: Their marks are added to the average; their weight never enters the
#: denominator. A course weighted 100% plus 5% bonus is still marked out of 100,
#: and the bonus is the 5 points that protect a slip somewhere else.
#:
#: A set rather than a single member because the distinction is the thing worth
#: naming, and because every site that needs it needs the same answer. Scattering
#: `!= BONUS` beside the six existing `!= FINAL` checks is how those two
#: exclusions would quietly drift apart.
ADDITIVE_CATEGORIES: frozenset[str] = frozenset({GradeCategory.BONUS.value})


def is_additive(category) -> bool:
    """Return whether a category's marks add on top of the average rather than form it.

    Args:
        category: A `GradeCategory` or its string value.

    Returns:
        True for a category in `ADDITIVE_CATEGORIES` (bonus).
    """
    value = category.value if isinstance(category, GradeCategory) else category
    return value in ADDITIVE_CATEGORIES


def scoring_weight(weights: dict) -> float:
    """Return the total weight of the categories a course is marked out of.

    Args:
        weights: Category name to weight percentage.

    Returns:
        The sum of every non-additive category's weight: the average's denominator.
    """
    return sum(
        weight for category, weight in weights.items()
        if not is_additive(category)
    )

class GradeSchedule(str, Enum):
    """What a dated grade raises outside the gradebook (`grades.schedule_as`)."""

    #: Raises a task that closes itself when the score lands.
    TASK = "task"
    #: Draws a block on the calendar and nothing else. Nothing to tick off.
    EVENT = "event"


#: What a grade scheduled as an event is themed as. A midterm and a final get
#: their own card; anything else is a deadline.
SCHEDULE_EVENT_KINDS: dict[str, str] = {
    GradeCategory.MIDTERM.value: "midterm",
    GradeCategory.FINAL.value: "final",
}
DEFAULT_SCHEDULE_EVENT_KIND = "deadline"
"""Event kind for a grade-raised event whose category has no kind of its own."""

#: The lowest and highest a task's priority may be.
MIN_PRIORITY = 1
MAX_PRIORITY = 5

#: What a task gets when nothing says otherwise: the middle of the scale, so
#: there is room to raise and lower from it. Coursework whose category is not
#: listed below lands here too -- an assignment, a lab, a quiz -- which is the
#: ordinary case rather than a fallback.
DEFAULT_PRIORITY = 3

#: Coursework that outranks the ordinary case. A final is the one date on a term
#: that cannot be made up; a midterm and a project are heavy enough to want
#: planning around, without being unrecoverable.
#:
#: Only the exceptions are listed. Spelling out every category would mean a new
#: one silently getting no priority at all, where falling through to the middle
#: of the scale is the right answer for anything unclassified.
CATEGORY_PRIORITY: dict[str, int] = {
    GradeCategory.FINAL.value: 5,
    GradeCategory.MIDTERM.value: 4,
    GradeCategory.PROJECT.value: 4,
}


def priority_for_category(category) -> int:
    """Return the starting priority of a task raised from a grade in this category.

    Args:
        category: A `GradeCategory` or its string value.

    Returns:
        The category's entry in `CATEGORY_PRIORITY`, else `DEFAULT_PRIORITY`.
    """
    value = getattr(category, "value", category)
    return CATEGORY_PRIORITY.get(value, DEFAULT_PRIORITY)
