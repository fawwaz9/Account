from enum import Enum

class Semester(str, Enum):
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
    """True when a category adds to the average instead of composing it."""
    value = category.value if isinstance(category, GradeCategory) else category
    return value in ADDITIVE_CATEGORIES


def scoring_weight(weights: dict) -> float:
    """Total weight of the categories the course is actually marked out of.

    The denominator, in other words -- bonus excluded. Every caller that used to
    write `sum(weights.values())` wants this instead, because that sum stopped
    meaning "out of how much" the moment an additive category existed.
    """
    return sum(
        weight for category, weight in weights.items()
        if not is_additive(category)
    )

class GradeSchedule(str, Enum):
    """How a dated grade shows up outside the gradebook.

    Two different things wear a date. An assignment due Friday is work: you want
    it on a list, and you want it to stop nagging once it is marked. A midterm on
    the 15th is not work you complete -- you sit it, and ticking it off afterwards
    means nothing. Forcing both through a task made the second read as a chore
    that never quite closed.
    """

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
