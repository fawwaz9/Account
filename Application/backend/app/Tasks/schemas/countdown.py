"""Response bodies for exam countdown (Phase 4 item 5, §4).

Inside a week of a midterm or final, that course's open work comes first.
Presentation over data already stored: calendar exams and tasks.
"""

from datetime import date, time
from uuid import UUID

from pydantic import BaseModel, Field


class CountdownTask(BaseModel):
    """One open task on the exam's course.

    Attributes:
        id: The task.
        title: Its title.
        due_date: When it is due, if it has a date.
        estimated_minutes: Its estimate, if any.
        priority: 1 to 5, 5 the most important.
    """
    id: UUID
    title: str
    due_date: date | None = None
    estimated_minutes: int | None = None
    priority: int = 3


class CountdownExam(BaseModel):
    """A midterm or final inside the window, with its course's open work.

    Attributes:
        event_id: The exam's event.
        title: The event's title.
        kind: "midterm" or "final".
        on_date: The day of the exam.
        start_time: Its local start, if timed.
        location: Where, if known.
        course_id: Its course, if it belongs to one.
        course_code: That course's code.
        days_left: Days from today; 0 is today.
        tasks: Up to `MAX_TASKS` of the course's open tasks due by the exam's day or
            undated: dated soonest first, undated last, then the most important.
        open_tasks: All of those tasks.
        estimated_minutes: The estimates on all of them added up.
    """
    event_id: UUID
    title: str
    kind: str
    on_date: date
    start_time: time | None = None
    location: str | None = None
    course_id: UUID | None = None
    course_code: str | None = None
    days_left: int
    tasks: list[CountdownTask] = Field(default_factory=list)
    open_tasks: int = 0
    estimated_minutes: int = 0


class ExamCountdown(BaseModel):
    """Every exam inside the window, soonest first.

    Attributes:
        window_days: How far ahead the countdown starts.
        exams: The exams, soonest first.
    """
    window_days: int
    exams: list[CountdownExam] = Field(default_factory=list)
