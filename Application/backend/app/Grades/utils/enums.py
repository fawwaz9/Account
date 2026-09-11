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
