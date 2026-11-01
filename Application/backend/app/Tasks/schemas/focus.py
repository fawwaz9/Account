"""Request and response bodies for focus sessions (Phase 4 item 4, §4, §16).

A timer tagged per course, building hours studied against grades. Single-user:
nothing here is shared or compared with anyone.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class FocusStart(BaseModel):
    """What a session is for.

    Attributes:
        course_id: One of your courses, or null for focus on nothing in particular.
    """
    course_id: UUID | None = None


class FocusSession(BaseModel):
    """One session.

    Attributes:
        id: The session.
        course_id: Its course, if any.
        course_code: That course's code.
        started_at: When it started, naive UTC.
        ended_at: When it stopped; null while running.
        minutes: Minutes focused; null while running.
    """
    id: UUID
    course_id: UUID | None = None
    course_code: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    minutes: int | None = None


class CourseFocus(BaseModel):
    """Focus on one course, with its grade for the chart.

    Attributes:
        course_id: The course; null for focus on no course.
        course_code: Its code, or "No course".
        minutes_this_week: Minutes this week, Monday to today.
        minutes_term: Minutes on it in all, since the term began.
        grade: The course's grade now; null with nothing marked or for no course.
    """
    course_id: UUID | None = None
    course_code: str
    minutes_this_week: int = 0
    minutes_term: int = 0
    grade: float | None = None


class FocusSummary(BaseModel):
    """The running session, and focus per course.

    Attributes:
        running: The session under way, if any.
        courses: This term's courses (and focus on no course), most focused first.
        total_this_week: Minutes this week across them all.
    """
    running: FocusSession | None = None
    courses: list[CourseFocus] = Field(default_factory=list)
    total_this_week: int = 0
