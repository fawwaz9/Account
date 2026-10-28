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
    """

    course_key: str | None
    floor: int
    distributions: list[TermDistribution]
    your_grade: float | None
    your_bucket: int | None
