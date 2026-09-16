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
    #: items, which is why the ranking does not depend on it.
    estimated_minutes: int | None = None
    #: Leverage per hour, null when there is no estimate. Never defaulted: a
    #: missing estimate sorts as free or infinite and both are lies.
    per_hour: float | None = None


class CheapestPath(BaseModel):
    """What is left in a course, ranked by what it is worth doing."""

    target: float
    current: float
    #: The average if everything outstanding went perfectly.
    best: float
    #: Whether the target is still arithmetically available at all.
    reachable: bool
    #: Ranked by leverage, which is the one figure known for every item.
    items: list[RemainingItem] = Field(default_factory=list)
    #: The best rate among items that carry an estimate, named only when at
    #: least two do -- "best value" of a list of one compares nothing.
    best_value_grade_id: UUID | None = None
    estimated_count: int = 0
    unestimated_count: int = 0
