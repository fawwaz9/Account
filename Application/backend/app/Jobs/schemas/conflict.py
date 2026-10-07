"""Shifts that collide with, or crowd, an exam (Phase 2 item 14)."""
from datetime import date, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class ShiftConflict(BaseModel):
    """One shift against one exam.

    ``overlap``: the shift runs into the exam. ``crowds``: it ends less than
    your buffer before the exam starts -- the night before, or the morning of.
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
    buffer_hours: int
    conflicts: list[ShiftConflict]
