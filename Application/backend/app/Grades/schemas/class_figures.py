"""Schemas for what other students' answers say about a course (Phase 3 items 3 and 5)."""
from pydantic import BaseModel


class GradeBandOut(BaseModel):
    """One 5-point band of a term's grade counts.

    Attributes:
        bucket: The band's lower bound: 0 for below 50, then 50, 55 ... 95.
        contributors: Grades counted in the band.
    """

    bucket: int
    contributors: int


class TermDistribution(BaseModel):
    """One closed term's grade counts for a course, above the floor.

    Attributes:
        term_code: The term, such as "2025W1".
        term_label: The term as read, such as "Fall 2025".
        contributors: Grades counted across every band.
        median_bucket: The band holding the middle grade.
        bands: The bands that hold any grade, lowest first.
    """

    term_code: str
    term_label: str
    contributors: int
    median_bucket: int
    bands: list[GradeBandOut]


class CourseIntelOut(BaseModel):
    """What past students' term reviews say about a course; each figure None below the floor.

    Attributes:
        hours_answers: People who gave their weekly hours.
        hours_median: Their median hours a week, to one decimal.
        difficulty_answers: People who rated difficulty.
        difficulty_mean: Mean difficulty out of 5, to one decimal.
        clarity_answers: People who rated the instructor's clarity.
        clarity_mean: Mean clarity out of 5, to one decimal.
        again_answers: People who said whether they would take it again.
        again_share: Whole percentage of them who said yes.
    """

    hours_answers: int | None
    hours_median: float | None
    difficulty_answers: int | None
    difficulty_mean: float | None
    clarity_answers: int | None
    clarity_mean: float | None
    again_answers: int | None
    again_share: int | None


class ClassFigures(BaseModel):
    """What other students' shared answers say about one of the caller's courses.

    Attributes:
        course_key: The key the course is counted under, such as "UBCV CPSC 221";
            None when its code isn't a course code, so nothing can be shown.
        floor: How many people a figure needs before it is shown.
        distributions: Closed terms' grade counts, newest first; empty while none
            has reached the floor.
        your_grade: The caller's own result in this course (final, else running
            average); None with nothing marked.
        your_bucket: The band `your_grade` falls in; None without one.
        intel: What past students' reviews say; None while no figure has reached the
            floor.
    """

    course_key: str | None
    floor: int
    distributions: list[TermDistribution]
    your_grade: float | None
    your_bucket: int | None
    intel: CourseIntelOut | None = None
