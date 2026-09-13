from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class ReminderBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    #: Local wall time, not UTC. "Remind me at 09:00" means nine o'clock where
    #: the student is, and should still mean that after the clocks change.
    remind_at: datetime
    course_id: UUID | None = None

    @model_validator(mode="after")
    def validate_reminder(self):
        if self.title.strip() == "":
            raise ValueError("A reminder needs something to say")
        if self.remind_at.tzinfo is not None:
            # An offset here would be a client sending UTC, which would then be
            # compared against local time and fire at the wrong hour.
            raise ValueError("Send the local time, without an offset")
        return self


class ReminderCreate(ReminderBase):
    pass


class ReminderUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    remind_at: datetime | None = None
    course_id: UUID | None = None


class Reminder(ReminderBase):
    id: UUID = Field(default_factory=uuid4)
    fired_at: datetime | None = None
    dismissed_at: datetime | None = None
    created_at: datetime | None = None
    #: Denormalised, so a banner can say "CPSC 210" without the client holding
    #: every course to look it up.
    course_code: str | None = None
    #: True when its moment has passed and nobody has dismissed it. Computed
    #: against the student's own local now, which the client cannot be trusted
    #: to agree on.
    due: bool = False

    class Config:
        from_attributes = True
