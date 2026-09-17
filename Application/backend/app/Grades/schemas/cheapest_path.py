from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class RemainingItem(BaseModel):
    """One unmarked item, and what doing it is worth."""

    grade_id: UUID
    name: str
    category: str
    max_score: float
    due_date: date | None = None
    #: Points of final course average this item still controls: the difference
    #: between finishing it perfectly and not finishing it at all.
    leverage: float = Field(..., description="Points of final average at stake")
    #: The student's own estimate, off the task this grade raised. Null for most
    #: items today, and the ranking leads on it -- so an item that has one
    #: outranks every item that does not, however small it is.
    estimated_minutes: int | None = None
    #: Leverage per hour, null when there is no estimate. Never defaulted: a
    #: missing estimate sorts as free or infinite and both are lies, so an
    #: unrated item is ordered below the rated ones instead of among them.
    per_hour: float | None = None


class CheapestPath(BaseModel):
    """The three items in a course most worth doing next."""

    target: float
    current: float
    #: The average if everything outstanding went perfectly.
    best: float
    #: Whether the target is still arithmetically available at all.
    reachable: bool
    #: The top three, ranked by points per hour and then by points. Capped
    #: server-side so the rule is one thing in one place with a test on it,
    #: rather than a slice in the component that nothing checks.
    items: list[RemainingItem] = Field(default_factory=list)
    #: How many were outstanding before the cut, so the panel can say which
    #: three of how many these are.
    remaining_count: int = 0
    #: Both counted over the three shown, not over everything outstanding.
    estimated_count: int = 0
    unestimated_count: int = 0
