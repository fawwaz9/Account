"""The digest: one deterministic summary of a student's day (Phase 4 items 6 and 7).

The Today card, the push briefing, the BYOAI endpoint and the MCP route all read
this one body, so they can never disagree. It carries no money figure (D8): it
may leave the app through the student's own assistant.
"""

from datetime import date, time

from pydantic import BaseModel, Field


class DigestEvent(BaseModel):
    """Something on today's calendar.

    Attributes:
        title: The event's title.
        kind: Its kind ("lecture", "midterm", "shift", ...).
        start_time: Local start; None for all day.
        end_time: Local end, if any.
        location: Where, if known.
        course_code: Its course's code, if any.
    """
    title: str
    kind: str
    start_time: time | None = None
    end_time: time | None = None
    location: str | None = None
    course_code: str | None = None


class DigestTask(BaseModel):
    """A task due today or overdue.

    Attributes:
        title: The task.
        course_code: Its course's code, if any.
        due_date: When it was due.
        due_time: The time of day, if any.
        estimated_minutes: Its estimate, if any.
    """
    title: str
    course_code: str | None = None
    due_date: date | None = None
    due_time: time | None = None
    estimated_minutes: int | None = None


class DigestExam(BaseModel):
    """An exam inside the countdown window.

    Attributes:
        name: "CPSC 310 midterm", or the event's title without a course.
        on_date: The day.
        days_left: 0 is today.
        open_tasks: Open work on its course due by then.
        estimated_minutes: That work's estimates added up.
    """
    name: str
    on_date: date
    days_left: int
    open_tasks: int = 0
    estimated_minutes: int = 0


class DigestRisk(BaseModel):
    """A deadline your usual pace falls short of.

    Attributes:
        due_date: The day.
        titles: Up to three of the tasks due then.
        shortfall_minutes: How far short your usual pace falls by then.
        includes_earlier: Whether that shortfall counts work due before this day too.
    """
    due_date: date
    titles: list[str] = Field(default_factory=list)
    shortfall_minutes: int
    includes_earlier: bool = False


class DigestWeek(BaseModel):
    """This Monday-to-Sunday week's load.

    Attributes:
        booked_minutes: Every timed event this week.
        estimated_minutes: Estimates on tasks due this week, scaled when asked for.
        tasks_due: Tasks due this week.
    """
    booked_minutes: int = 0
    estimated_minutes: int = 0
    tasks_due: int = 0


class Digest(BaseModel):
    """A student's day, as one deterministic summary.

    Attributes:
        on_date: The student's today.
        events: Today's calendar, all-day first, then by start.
        due_today: Open tasks due today.
        overdue: Open tasks past due, oldest first, up to `MAX_LISTED`.
        overdue_count: All of them.
        exams: Midterms and finals in the next week.
        at_risk: Deadlines your pace falls short of; empty before it knows your pace.
        week: This week's load.
        free_minutes_today: Free time left today inside your study window.
        longest_free_start: When today's longest free block starts, if any.
        longest_free_minutes: How long it is.
        text: The whole digest in plain sentences, for a push or an assistant.
    """
    on_date: date
    events: list[DigestEvent] = Field(default_factory=list)
    due_today: list[DigestTask] = Field(default_factory=list)
    overdue: list[DigestTask] = Field(default_factory=list)
    overdue_count: int = 0
    exams: list[DigestExam] = Field(default_factory=list)
    at_risk: list[DigestRisk] = Field(default_factory=list)
    week: DigestWeek = Field(default_factory=DigestWeek)
    free_minutes_today: int = 0
    longest_free_start: time | None = None
    longest_free_minutes: int = 0
    text: str = ""
