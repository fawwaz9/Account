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