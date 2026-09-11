from datetime import date, time
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from app.Calendar.utils.recurrence import FREQUENCIES, WEEKDAY_CODES


class EventKind(str, Enum):
    """What an event is, for the purpose of how it reads on the calendar.

    A string rather than a table because, unlike accounts or spend categories,
    each of these has behaviour attached -- a midterm is themed differently and
    sorts differently from a lecture -- so a user-defined one would have nothing
    to do.
    """

    LECTURE = "lecture"
    LAB = "lab"
    DISCUSSION = "discussion"
    MIDTERM = "midterm"
    FINAL = "final"
    DEADLINE = "deadline"
    PERSONAL = "personal"


#: The kinds a course's timetable is built from.
CLASS_KINDS = (EventKind.LECTURE, EventKind.LAB, EventKind.DISCUSSION)

#: The kinds that replace the class card with an exam-themed one.
EXAM_KINDS = (EventKind.MIDTERM, EventKind.FINAL)


class Frequency(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class Weekday(str, Enum):
    MO = "MO"
    TU = "TU"
    WE = "WE"
    TH = "TH"
    FR = "FR"
    SA = "SA"
    SU = "SU"


class Recurrence(BaseModel):
    """How an event repeats. Absent on the event means it happens once."""

    freq: Frequency
    interval: int = Field(default=1, ge=1, le=52, description="Every N days/weeks/months")
    byday: list[Weekday] = Field(
        default_factory=list,
        description="Weekly only. Empty means the weekday the event starts on.",
    )
    until: date | None = Field(default=None, description="Inclusive last date")
    count: int | None = Field(default=None, ge=1, le=500, description="Number of occurrences")

    @model_validator(mode="after")
    def validate_recurrence(self):
        # Two ends would have to be reconciled on every read, and the answer
        # ("whichever comes first") is one nobody means when they set both.
        if self.until is not None and self.count is not None:
            raise ValueError("A repeat ends on a date or after a number of times, not both")

        if self.byday and self.freq != Frequency.WEEKLY:
            raise ValueError("Weekdays only apply to a weekly repeat")

        return self


class EventBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    kind: EventKind = Field(default=EventKind.PERSONAL)
    course_id: UUID | None = Field(default=None, description="Set when the event belongs to a course")
    location: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)
    #: The first date the event happens. For a repeat this anchors the rule as
    #: well, which is why a weekly rule with no weekdays means "this weekday".
    starts_on: date
    #: Both absent means an all-day event. Times are local wall-clock: a 10:00
    #: lecture is at 10:00 in the week the clocks change too.
    start_time: time | None = None
    end_time: time | None = None
    recurrence: Recurrence | None = None

    @model_validator(mode="after")
    def validate_event(self):
        if self.title.strip() == "":
            raise ValueError("An event needs a title")

        if self.end_time is not None and self.start_time is None:
            raise ValueError("An event with an end time needs a start time")

        if self.start_time is not None and self.end_time is not None:
            if self.end_time <= self.start_time:
                raise ValueError("An event cannot end before it starts")

        if self.recurrence and self.recurrence.until is not None:
            if self.recurrence.until < self.starts_on:
                raise ValueError("A repeat cannot end before the event starts")

        return self


class EventCreate(EventBase):
    pass


class EventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    kind: EventKind | None = None
    course_id: UUID | None = None
    location: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)
    starts_on: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    #: Sending null clears the repeat, leaving a one-off on `starts_on`.
    recurrence: Recurrence | None = None


class Event(EventBase):
    id: UUID = Field(default_factory=uuid4)
    #: The rule's cancelled dates -- a reading week, a lecture that did not run.
    skipped_dates: list[date] = Field(default_factory=list)

    class Config:
        from_attributes = True


class EventOccurrence(BaseModel):
    """One date a series actually falls on.

    Materialised per read and never stored, so it carries the event's id rather
    than one of its own. `(event_id, on_date)` is what identifies it.
    """

    event_id: UUID
    on_date: date
    title: str
    kind: EventKind
    start_time: time | None = None
    end_time: time | None = None
    location: str | None = None
    notes: str | None = None
    course_id: UUID | None = None
    #: Denormalised so the calendar can label a block "CPSC 221" without the
    #: client holding the whole course list to look it up.
    course_code: str | None = None
    #: True when this came from a rule, so the UI can say "every Monday" and ask
    #: whether an edit means this date or all of them.
    repeats: bool = False


class ClassMeeting(BaseModel):
    """One recurring block of a course's timetable, as entered in the form."""

    kind: EventKind = Field(default=EventKind.LECTURE)
    days: list[Weekday] = Field(..., min_length=1, description="Days of the week it meets")
    start_time: time
    end_time: time
    location: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def validate_meeting(self):
        if self.end_time <= self.start_time:
            raise ValueError("A class cannot end before it starts")
        if self.kind not in CLASS_KINDS:
            allowed = ", ".join(kind.value for kind in CLASS_KINDS)
            raise ValueError(f"A class meeting must be one of: {allowed}")

        return self


class ClassScheduleCreate(BaseModel):
    """A course's whole timetable, replacing whatever was there before.

    Replacing rather than appending: this is the "add to calendar" form, and
    submitting it twice should leave one timetable rather than two overlapping
    copies of it.
    """

    meetings: list[ClassMeeting] = Field(default_factory=list)
    #: Default to the course's own dates; overridable for a course whose term
    #: dates are not filled in.
    starts_on: date | None = None
    ends_on: date | None = None

    @model_validator(mode="after")
    def validate_schedule(self):
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("A term cannot end before it starts")

        return self


# Kept honest against the engine: the enums above are what the API accepts, and
# the engine is what has to understand them.
assert {frequency.value for frequency in Frequency} == set(FREQUENCIES)
assert {day.value for day in Weekday} == set(WEEKDAY_CODES)
