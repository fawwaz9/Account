"""Response bodies for the deadline spending guard's detection (Phase 4 item 13, §13.5).

Calendar into money, never the other way: crunch weeks from exams, deadlines and
work due, and the student's own spending in past crunch weeks against the rest.
Silent until two crunch weeks of history; no generic priors, no peer data.
"""

from datetime import date

from pydantic import BaseModel, Field


class UpcomingCrunch(BaseModel):
    """The crunch week ahead.

    Attributes:
        starts_on: Its Monday.
        days_away: Days from today to that Monday.
        exams: Midterms and finals in it.
        deadlines: Deadline events in it.
        tasks: Tasks due in it.
    """
    starts_on: date
    days_away: int
    exams: int = 0
    deadlines: int = 0
    tasks: int = 0


class CategoryLift(BaseModel):
    """A category you spend more on in crunch weeks.

    Attributes:
        category: Its name.
        crunch_weekly: Average a crunch week.
        usual_weekly: Average any other week.
        lift: The first over the second.
        crunch_weeks: Crunch weeks it is averaged over.
    """
    category: str
    crunch_weekly: float
    usual_weekly: float
    lift: float
    crunch_weeks: int


class SpendingGuard(BaseModel):
    """What the guard has learned, and whether a crunch week is coming.

    Attributes:
        ready: True once `needed_crunch_weeks` crunch weeks are in the history.
        crunch_weeks: Past crunch weeks found.
        needed_crunch_weeks: Crunch weeks needed before it speaks.
        upcoming: The crunch week starting in the next seven days, if any; never the
            week already under way.
        lifts: Categories with real lift (above `MIN_LIFT`, over at least
            `MIN_CATEGORY_WEEKS` crunch weeks), biggest first.
        note: The framing, in words: pre-allocation, not permission.
    """
    ready: bool
    crunch_weeks: int
    needed_crunch_weeks: int
    upcoming: UpcomingCrunch | None = None
    lifts: list[CategoryLift] = Field(default_factory=list)
    note: str = ""
