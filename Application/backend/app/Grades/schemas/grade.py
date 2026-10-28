"""Request and response schemas for grades: the assessed work in a course."""

from datetime import date, time
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, model_validator

from app.Grades.utils.enums import GradeCategory, GradeSchedule

#: Kept in step with grade_service.MAX_SCORE_MULTIPLE; defined here to avoid a
#: schema -> service import.
MAX_SCORE_MULTIPLE = 2.0

class GradeBase(BaseModel):
    """A grade's fields and the rules a complete grade must satisfy.

    Attributes:
        name: Assessment name, 1-100 characters, not blank.
        score: Points earned, 0 or more; null while unmarked. May exceed `max_score`
            (bonus) up to `MAX_SCORE_MULTIPLE` times it.
        max_score: Points possible, above 0.
        category: The grade category.
        due_date: When the work is due; a dated grade raises a task or a calendar block.
        due_time: Time of day on `due_date`; null means end of day for a task and all
            day for an event. Needs `due_date`.
        duration_minutes: Length of the calendar block, 5-1440 minutes; needs
            `due_time`.
        schedule_as: "task" or "event": what the date raises. Ignored without a date.
        excluded: Dropped: kept on the course but out of every average.
    """
    name: str = Field(..., min_length=1, max_length=100, description="The name of the grade (e.g., Midterm Exam, Final Project)")
    # Optional so an assignment can be added before it has been marked. Every
    # averaging function already skips grades whose score is None, and the
    # column is nullable; only this schema was forcing a score up front.
    score: float | None = Field(default=None, ge=0, description="The score obtained, or null if not yet graded")
    max_score: float = Field(..., gt=0, description="The maximum possible score for the grade")
    category: GradeCategory = Field(..., description="The category of the grade (e.g., Assignment, Lab, Quiz, etc.)")
    # When the work is due, as opposed to when it was marked.
    due_date: date | None = Field(default=None, description="When the work is due, if it has a deadline")
    # The time of day, where it is known. Null is not "midnight" -- it means no
    # particular time, which the task side reads as the end of the day and the
    # calendar side as an all-day block.
    due_time: time | None = Field(
        default=None,
        description="The time of day it is due or happens, if there is a particular one",
    )
    # A length rather than an end time. "The midterm is two hours" is what a
    # student knows, and an end derived from a start cannot contradict it --
    # where a second stored column can, and would need a rule saying so.
    #
    # Floor of 5 because anything less is a slipped digit; ceiling of a full day
    # because a block cannot outrun the date it sits on.
    duration_minutes: int | None = Field(
        default=None, ge=5, le=1440,
        description="How long a calendar-bound grade runs, in minutes",
    )
    # What that date means. An assignment is work to tick off; a midterm is
    # something to sit, which is a calendar block and not a chore. Ignored
    # without a date.
    schedule_as: GradeSchedule = Field(
        default=GradeSchedule.TASK,
        description="task: raises a task that closes when marked. event: a calendar block only.",
    )
    #: Shown on the course but left out of every average, for a mark a professor
    #: has dropped. Kept rather than deleted: it happened, and which marks are
    #: dropped can change as more work comes back.
    excluded: bool = Field(
        default=False,
        description="Kept on the course but left out of the average",
    )

    @model_validator(mode="after")
    def validate_grade_logic(self):
        """Enforce the cross-field rules of a complete grade.

        Returns:
            The model, unchanged.

        Raises:
            ValueError: If the name is blank, the score exceeds `MAX_SCORE_MULTIPLE`
                times
                the maximum, a time has no date, or a length has no time (a 422).
        """
        if self.name.strip() == "":
            raise ValueError("Grade name cannot be empty")
        # Bonus marks are real, so a score may exceed its max -- but not by an
        # implausible multiple, which catches a slipped digit.
        if self.score is not None and self.score > self.max_score * MAX_SCORE_MULTIPLE:
            raise ValueError(f"Score cannot exceed {MAX_SCORE_MULTIPLE:g}x the max score")

        # The same wording tasks use, because it is the same mistake: a time on
        # its own says when but not when *what*, and nothing downstream could
        # place it.
        if self.due_time is not None and self.due_date is None:
            raise ValueError("A time of day needs a date to go with it")

        # An all-day block has no length, so a duration with nothing to start
        # from could not be drawn and could not be corrected either.
        if self.duration_minutes is not None and self.due_time is None:
            raise ValueError("A length needs a start time to run from")

        return self
 
class GradeCreate(GradeBase):
    """Request body for adding a grade; the fields and rules of `GradeBase`."""
    pass

class GradeUpdate(BaseModel):
    """Request body for editing a grade; omitted fields stay as they are.

    Per-field limits only. `grade_service.update_grade` checks the score multiple and
    the time and length rules on the merged result, and clears a time and length when
    their date or time is removed.

    Attributes:
        name: New name, 1-100 characters.
        score: New score, 0 or more; null marks it unmarked again.
        max_score: New maximum, above 0.
        category: New category; the grade's weight follows it.
        due_date: New due date; null removes it, with its time and length.
        due_time: New time of day; null removes it, with its length.
        duration_minutes: New block length, 5-1440 minutes.
        schedule_as: "task" or "event"; null leaves it unchanged.
        excluded: Drop the grade from, or restore it to, every average.
    """
    name: str | None = Field(default=None, min_length=1, max_length=100)
    score: float | None = Field(default=None, ge=0)
    max_score: float | None = Field(default=None, gt=0)
    category: GradeCategory | None = Field(default=None)
    due_date: date | None = Field(default=None)
    due_time: time | None = Field(default=None)
    duration_minutes: int | None = Field(default=None, ge=5, le=1440)
    schedule_as: GradeSchedule | None = Field(default=None)
    excluded: bool | None = Field(default=None)

class Grade(GradeBase):
    """A grade as the API returns it.

    Inherits `GradeBase` and its validator, so every stored grade is re-checked on the
    way out.

    Attributes:
        id: The grade's id.
        weight: Its category's weight in the course, 0-100.
    """
    id: UUID = Field(default_factory=uuid4)
    weight: float = Field(..., ge=0, le=100, description="The weight assigned by the grade category")

    class Config:
        """Pydantic v1-style settings: build the model from object attributes."""
        from_attributes = True
