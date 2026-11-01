"""Response bodies for the deadline spending guard's detection (Phase 4 item 13, §13.5).

Calendar into money, never the other way: crunch weeks from exams, deadlines and
work due, and the student's own spending in past crunch weeks against the rest.
Silent until two crunch weeks of history; no generic priors, no peer data.
"""

from datetime import date
from uuid import UUID

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
        category_id: The category.
        category: Its name.
        crunch_weekly: Average a crunch week.
        usual_weekly: Average any other week.
        lift: The first over the second.
        crunch_weeks: Crunch weeks it is averaged over.
        set_aside: What you set aside for the week ahead, if you did.
        dismissed: True when you waved it off for the week ahead.
    """
    category_id: UUID | None = None
    category: str
    crunch_weekly: float
    usual_weekly: float
    lift: float
    crunch_weeks: int
    set_aside: float | None = None
    dismissed: bool = False


class ReportLine(BaseModel):
    """One category of the last crunch week you set money aside for.

    Attributes:
        category: Its name.
        set_aside: What you set aside.
        spent: What you spent in it that week.
    """
    category: str
    set_aside: float
    spent: float


class AllocateIn(BaseModel):
    """Money set aside in a category for a crunch week.

    Attributes:
        category_id: One of your categories.
        week_start: The crunch week's Monday: this week's or next.
        amount: Dollars, 0 to 10,000.
    """
    category_id: UUID
    week_start: date
    amount: float = Field(..., ge=0, le=10_000)


class DismissIn(BaseModel):
    """A suggestion waved off for one week.

    Attributes:
        category_id: One of your categories.
        week_start: The crunch week's Monday: this week's or next.
    """
    category_id: UUID
    week_start: date


class SpendingGuard(BaseModel):
    """What the guard has learned, and whether a crunch week is coming.

    Attributes:
        ready: True once `needed_crunch_weeks` crunch weeks are in the history.
        crunch_weeks: Past crunch weeks found.
        needed_crunch_weeks: Crunch weeks needed before it speaks.
        upcoming: The crunch week starting in the next seven days, if any; never the
            week already under way.
        lifts: Categories with real lift (above `MIN_LIFT`, over at least
            `MIN_CATEGORY_WEEKS` crunch weeks), biggest first; a category waved off
            three times is left out.
        report_week: The last finished week you set money aside for, if any.
        report: What you set aside and spent there, per category.
        note: The framing, in words: pre-allocation, not permission.
    """
    ready: bool
    crunch_weeks: int
    needed_crunch_weeks: int
    upcoming: UpcomingCrunch | None = None
    lifts: list[CategoryLift] = Field(default_factory=list)
    report_week: date | None = None
    report: list[ReportLine] = Field(default_factory=list)
    note: str = ""
