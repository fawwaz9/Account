"""Response bodies for cross-room correlations, non-financial (Phase 4 item 8, §4).

Academic against body, week by week. The financial silo (§13.3) excludes every
correlation involving money, so no money figure is read or shown. Strength in
words, the number of weeks behind it, and never a claim of cause (§15).
"""

from datetime import date

from pydantic import BaseModel, Field


class WeekPair(BaseModel):
    """One week's two figures.

    Attributes:
        week_start: The Monday.
        body: Exertion points that week.
        academic: The academic figure that week (tasks finished, or minutes of work).
    """
    week_start: date
    body: int
    academic: int


class Correlation(BaseModel):
    """One pair, read across the weeks.

    Attributes:
        key: "tasks" or "minutes".
        body_label: What the body figure is.
        academic_label: What the academic figure is.
        weeks: Weeks behind it.
        coefficient: Pearson's r, -1 to 1, to two places; None when either side
            never changes.
        strength: "no clear link", "weak", "moderate" or "strong".
        reading: One sentence, describing what moves together and never a cause.
        pairs: The weeks, oldest first, for the chart.
    """
    key: str
    body_label: str
    academic_label: str
    weeks: int
    coefficient: float | None = None
    strength: str
    reading: str
    pairs: list[WeekPair] = Field(default_factory=list)


class Correlations(BaseModel):
    """Every pair, once there are enough weeks of both rooms.

    Attributes:
        ready: False until `needed_weeks` weeks hold both rooms' data.
        weeks_of_both: Weeks counted so far.
        needed_weeks: Weeks needed before anything is said.
        correlations: The pairs; empty until ready.
        caution: What a correlation is not, in words.
    """
    ready: bool
    weeks_of_both: int
    needed_weeks: int
    correlations: list[Correlation] = Field(default_factory=list)
    caution: str = ""
