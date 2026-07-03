from enum import Enum

class Semester(str, Enum):
    FALL = "Fall"
    WINTER = "Winter"
    SUMMER = "Summer"
    SPRING = "Spring"

class GradeCategory(str, Enum):
    ASSIGNMENT = "Assignment"
    LAB = "Lab"
    QUIZ = "Quiz"
    MIDTERM = "Midterm"
    FINAL = "Final"
    PARTICIPATION = "Participation"
    PROJECT = "Project"
    OTHER = "Other"