"""Response bodies for shifts that overlap or crowd an exam.

`conflict_service` reads the calendar's own occurrences, so skipped dates,
blackouts and repeating shifts agree with what the calendar shows.
"""
from datetime import date, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class ShiftConflict(BaseModel):
    """One shift set against one exam it overlaps or crowds.

    Attributes:
        kind: "overlap" when the shift and the exam share any time; "crowds" when
            the shift ends before the exam starts, but within the user's buffer.
        shift_event_id: The shift's event id.
        shift_on: The date of the shift occurrence.
        shift_start: Local start; None for an untimed shift, taken as all day.
        shift_end: Local end; before the start for an overnight shift.
        job_id: The shift's job.
        job_name: That job's name.
        exam_event_id: The exam's event id.
        exam_title: The exam's title.
        exam_kind: "midterm" or "final".
        exam_on: The exam's date.
        exam_start: Local start; None while unknown, taken as 08:00.
        course_code: The exam's course code.
        hours_between: Hours from the shift's end to the exam's start, 1 dp; 0
            for an overlap.
    """

    kind: Literal["overlap", "crowds"]
    shift_event_id: UUID
    shift_on: date
    shift_start: time | None
    shift_end: time | None
    job_id: UUID | None
    job_name: str | None
    exam_event_id: UUID
    exam_title: str
    exam_kind: str
    exam_on: date
    exam_start: time | None
    course_code: str | None
    #: Hours from the shift's end to the exam's start; 0 for an overlap.
    hours_between: float


class ShiftConflicts(BaseModel):
    """Every shift-exam conflict in a window, with the buffer that was applied.

    Attributes:
        buffer_hours: The user's exam buffer in hours, from Settings; 0 flags
            overlaps only.
        conflicts: The conflicts, ordered by exam date and start, then shift date.
    """

    buffer_hours: int
    conflicts: list[ShiftConflict]
