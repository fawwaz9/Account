"""Request and response bodies for grade scenarios (Phase 4 item 10, §13.6).

A scenario sets a score on any of a course's unmarked assessments and assumes one
score for the rest; the answer is the projected grade, through exactly the engine
every other projection uses. Nothing is stored.
"""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

#: More assessments than any course holds; a body past it is not a real scenario.
MAX_SCENARIO_SCORES = 200


class GradeScenarioIn(BaseModel):
    """A what-if for one course.

    Attributes:
        assume: The percentage every unmarked assessment not in `scores` scores,
            0-100. Weighted categories with nothing in them count at it whole.
        scores: Grade id to the percentage it scores, 0-100. Only this course's
            unmarked, counted assessments may be named.
    """
    assume: float = Field(..., ge=0, le=100)
    scores: dict[UUID, float] = Field(default_factory=dict, max_length=MAX_SCENARIO_SCORES)

    @field_validator("scores")
    @classmethod
    def scores_in_range(cls, scores: dict[UUID, float]) -> dict[UUID, float]:
        """Refuse a score outside 0-100 rather than computing with it (§13.6).

        Args:
            scores: The scores as sent.

        Returns:
            The same scores.

        Raises:
            ValueError: If any is below 0 or above 100.
        """
        for value in scores.values():
            if not 0 <= value <= 100:
                raise ValueError("Each score must be between 0 and 100")
        return scores


class ScenarioItem(BaseModel):
    """One unmarked assessment, and the score the scenario gave it.

    Attributes:
        grade_id: The assessment.
        name: Its name.
        category: Its grade category.
        max_score: Points possible.
        due_date: When it is due, if known.
        percent: The percentage counted for it in this scenario.
        set: True when the scenario named it; False when it took `assume`.
    """
    grade_id: UUID
    name: str
    category: str
    max_score: float
    due_date: date | None = None
    percent: float
    set: bool = False


class GradeScenario(BaseModel):
    """What a course finishes at under a scenario, beside where it stands.

    Attributes:
        course_id: The course.
        current: The course's grade now, from marked work only.
        projected: The grade with every unmarked assessment at its scenario score.
        letter: The letter grade the projection reaches.
        best: The grade with everything outstanding at full marks.
        worst: The grade with everything outstanding at zero.
        assume: The percentage the unnamed assessments took.
        items: The unmarked assessments, by due date, then name.
        empty_categories: Weighted categories with nothing in them yet; each counted
            at `assume` whole.
        assumptions: Every assumption the projection made, in words.
    """
    course_id: UUID
    current: float
    projected: float
    letter: str
    best: float
    worst: float
    assume: float
    items: list[ScenarioItem] = Field(default_factory=list)
    empty_categories: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
