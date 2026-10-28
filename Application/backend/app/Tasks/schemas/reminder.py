"""Request and response bodies for reminders, which notify at a moment rather than wait.

`remind_at` is naive local wall time, never UTC: "09:00" means nine o'clock
wherever the student is. `reminder_service` compares it with the user's local now.
"""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class ReminderBase(BaseModel):
    """Fields shared by a reminder's create body and its response.

    Attributes:
        title: What to be reminded of, 1-200 characters and not blank.
        notes: Free text, up to 2000 characters.
        remind_at: When it falls due, as naive local wall time; a UTC offset is
            refused.
        course_id: The course it concerns; None for none.
    """

    title: str = Field(..., min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    #: Local wall time, not UTC. "Remind me at 09:00" means nine o'clock where
    #: the student is, and should still mean that after the clocks change.
    remind_at: datetime
    course_id: UUID | None = None

    @model_validator(mode="after")
    def validate_reminder(self):
        """Refuse a blank title or a `remind_at` that carries a UTC offset.

        Returns:
            The validated model.

        Raises:
            ValueError: If the title is blank or `remind_at` is timezone-aware.

        Note:
            This also runs whenever a stored row is serialised as `Reminder`, so a row
            that breaks these rules makes its response fail.
        """
        if self.title.strip() == "":
            raise ValueError("A reminder needs something to say")
        if self.remind_at.tzinfo is not None:
            # An offset here would be a client sending UTC, which would then be
            # compared against local time and fire at the wrong hour.
            raise ValueError("Send the local time, without an offset")
        return self


class ReminderCreate(ReminderBase):
    """Request body for creating a reminder: the fields of `ReminderBase`."""

    pass


class ReminderUpdate(BaseModel):
    """Request body for editing a reminder; only the fields sent are changed.

    Moving `remind_at` re-arms the reminder: it counts as not yet shown, pushed or
    dismissed.

    Attributes:
        title: New text, 1-200 characters.
        notes: New notes, up to 2000 characters; null clears them.
        remind_at: New moment, as naive local wall time.
        course_id: New course; null clears it.
    """

    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    remind_at: datetime | None = None
    course_id: UUID | None = None


class Reminder(ReminderBase):
    """A reminder as the API returns it: the `ReminderBase` fields plus these.

    Attributes:
        id: The reminder's id.
        fired_at: When the app first showed it, naive UTC; None until then.
        pushed_at: When the scheduler pushed it to a device, naive UTC; the app
            skips its own notification for these.
        dismissed_at: When it was dismissed, naive UTC; None while active.
        created_at: When it was made, naive UTC.
        course_code: The linked course's code, so a banner can name it.
        due: True when `remind_at` has passed on the user's clock and it is not
            dismissed.
    """

    id: UUID = Field(default_factory=uuid4)
    fired_at: datetime | None = None
    #: Pushed to a device by the scheduler; the app skips its own system
    #: notification for these, so one reminder is not announced twice.
    pushed_at: datetime | None = None
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
        """Pydantic settings: allow building the model from an ORM row."""

        from_attributes = True
