"""Request and response bodies for calendar events, repeat rules and class timetables.

One event row covers a one-off or a whole series. `Recurrence` is the API's form
of the five `recur_*` columns, `EventOccurrence` is one expanded date, and
`ClassMeeting` and `ClassScheduleCreate` carry a course's timetable form.
"""

from datetime import date, time
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from app.Calendar.utils.recurrence import FREQUENCIES, WEEKDAY_CODES


class EventKind(str, Enum):
    """What an event is, which decides how the calendar themes and sorts it.

    Stored as its string value in `events.kind`. A fixed set rather than
    user-defined because each kind carries behaviour: exams get their own card,
    classes make up a timetable, and a shift belongs to a job.
    """

    LECTURE = "lecture"
    LAB = "lab"
    DISCUSSION = "discussion"
    MIDTERM = "midterm"
    FINAL = "final"
    DEADLINE = "deadline"
    PERSONAL = "personal"
    #: Paid work. A block like any other on the clock, and deliberately not one
    #: of the kinds below: it belongs to a job rather than a course, carries no
    #: academic weight, and a reading break does not cancel it.
    SHIFT = "shift"


#: The kinds a course's timetable is built from, and the only kinds a
#: `ClassMeeting` will accept.
#:
#: A shift is not among them and must not be: adding it would let the class
#: timetable form build a course out of shifts. What stops a timetable rewrite
#: from deleting shifts is a different guard -- `set_class_schedule` matches on
#: `course_id` as well, and a shift has none -- so the two are worth keeping
#: apart rather than trusting one to cover both.
CLASS_KINDS = (EventKind.LECTURE, EventKind.LAB, EventKind.DISCUSSION)

#: The kinds that replace the class card with an exam-themed one.
EXAM_KINDS = (EventKind.MIDTERM, EventKind.FINAL)

#: Kinds that belong to a job rather than to a course.
WORK_KINDS = (EventKind.SHIFT,)


class Frequency(str, Enum):
    """How often a repeat recurs; the API form of `recur_freq`."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class Weekday(str, Enum):
    """A weekday code, Monday to Sunday, as stored in `recur_byday`."""

    MO = "MO"
    TU = "TU"
    WE = "WE"
    TH = "TH"
    FR = "FR"
    SA = "SA"
    SU = "SU"


class Recurrence(BaseModel):
    """How an event repeats; the API form of the five `recur_*` columns.

    Attributes:
        freq: Daily, weekly or monthly.
        interval: Units of `freq` between occurrences, 1-52.
        byday: Weekdays a weekly repeat falls on; empty means the weekday of the
            event's `starts_on`. Only allowed when `freq` is weekly.
        until: Last date the repeat may fall on, inclusive; None for no end date.
        count: How many times the series runs in all, 1-500; None for no limit.
    """

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
        """Refuse two end conditions at once, or weekdays on a non-weekly repeat.

        Returns:
            The validated model.

        Raises:
            ValueError: If `until` and `count` are both set, or `byday` is set on a
                daily or monthly repeat.
        """
        # Two ends would have to be reconciled on every read, and the answer
        # ("whichever comes first") is one nobody means when they set both.
        if self.until is not None and self.count is not None:
            raise ValueError("A repeat ends on a date or after a number of times, not both")

        if self.byday and self.freq != Frequency.WEEKLY:
            raise ValueError("Weekdays only apply to a weekly repeat")

        return self


class EventBase(BaseModel):
    """Fields shared by an event's create body and its response.

    Attributes:
        title: Name shown on the calendar, 1-120 characters and not blank.
        kind: What the event is; defaults to personal.
        course_id: The course it belongs to; None for a personal event.
        location: Where it happens, up to 120 characters.
        notes: Free text, up to 1000 characters.
        starts_on: The date it happens, or the first date of a series, which also
            anchors the repeat rule.
        start_time: Local wall-clock start; None, with no `end_time`, means all day.
        end_time: Local wall-clock end, after `start_time`; needs a `start_time`.
        recurrence: How it repeats; None for a one-off.
        skipped_dates: Dates the series does not run.
    """

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
        """Check the title, the times, and the repeat's end against the start.

        Returns:
            The validated model.

        Raises:
            ValueError: If the title is blank, `end_time` is set without `start_time`
                or is not after it, or the repeat's `until` is before `starts_on`.

        Note:
            This also runs whenever a stored row is read out as `Event`, so a row that
            breaks these rules makes its response fail.
        """
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

    #: Dates the series does not run: a known cancellation, a week away. Set at
    #: setup rather than only by skipping occurrences after the fact.
    skipped_dates: list[date] = Field(default_factory=list)

class EventCreate(EventBase):
    """Request body for creating an event: the fields of `EventBase`."""

    pass


class EventUpdate(BaseModel):
    """Request body for editing an event; only the fields sent are changed.

    Attributes:
        title: New title, 1-120 characters; the service strips it.
        kind: New kind.
        course_id: New course; null detaches the event from its course.
        location: New location, up to 120 characters; null clears it.
        notes: New notes, up to 1000 characters; null clears it.
        starts_on: New date, or new first date of the series.
        start_time: New start time; null clears it.
        end_time: New end time; null clears it.
        recurrence: New repeat rule; null makes the event a one-off on `starts_on`.
        skipped_dates: Replaces the cancelled dates whole; null clears them.
    """

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
    #: Dates this series does not run, set while editing rather than only by
    #: cancelling occurrences one at a time afterwards.
    skipped_dates: list[date] | None = None


class Event(EventBase):
    """An event as the API returns it: the `EventBase` fields plus these.

    Attributes:
        id: The event's id.
        skipped_dates: The series' cancelled dates, ascending.
    """

    id: UUID = Field(default_factory=uuid4)
    #: The rule's cancelled dates -- a reading week, a lecture that did not run.
    skipped_dates: list[date] = Field(default_factory=list)

    class Config:
        """Pydantic settings: allow building the model from an ORM row."""

        from_attributes = True


class EventOccurrence(BaseModel):
    """One date an event falls on, expanded on read and never stored.

    It has no id of its own; `(event_id, on_date)` identifies it.

    Attributes:
        event_id: The event (one-off or series) this date belongs to.
        on_date: The date of this occurrence.
        title: The event's title.
        kind: The event's kind.
        start_time: Local start time; None for an all-day event.
        end_time: Local end time; None when the event has none.
        location: The event's location.
        notes: The event's notes.
        course_id: The event's course, if any.
        course_code: That course's code ("CPSC 221"), so the client needs no course
            list to label the block.
        job_id: The job a shift belongs to; None for anything else.
        repeats: True when the event has a repeat rule, so an edit can ask whether
            it means this date or the whole series.
        grade_id: The dated grade that produced this block; the gradebook owns it,
            so the calendar offers no delete.
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
    #: Set on a shift, the way course_id is set on a lecture. Carried here so
    #: reading a window of shifts needs no second query per occurrence.
    job_id: UUID | None = None
    #: True when this came from a rule, so the UI can say "every Monday" and ask
    #: whether an edit means this date or all of them.
    repeats: bool = False
    #: Set when a dated grade produced this block. The gradebook owns it, so the
    #: calendar offers no delete: removing it here would only bring it back the
    #: next time the grade was saved.
    grade_id: UUID | None = None


#: The longest gap a class can repeat on. Every eight weeks is already beyond
#: anything a timetable does; past that it is a mistake rather than a schedule.
MAX_MEETING_INTERVAL = 8


class ClassMeeting(BaseModel):
    """One repeating block of a course timetable, as entered in the timetable form.

    Attributes:
        kind: Lecture, lab or discussion (`CLASS_KINDS`); defaults to lecture.
        days: Weekdays it meets; at least one.
        start_time: Local start time.
        end_time: Local end time, after `start_time`.
        location: Room, up to 120 characters.
        interval: Every N weeks, 1-8; 1 is weekly, 2 fortnightly.
        first_on: First meeting of a non-weekly cycle, which sets which weeks are
            on-weeks; must fall on one of `days`. Ignored when `interval` is 1;
            None starts the cycle at the timetable's start date.
    """

    kind: EventKind = Field(default=EventKind.LECTURE)
    days: list[Weekday] = Field(..., min_length=1, description="Days of the week it meets")
    start_time: time
    end_time: time
    location: str | None = Field(default=None, max_length=120)
    interval: int = Field(
        default=1, ge=1, le=MAX_MEETING_INTERVAL,
        description="Every N weeks. 1 is weekly, 2 is fortnightly",
    )
    #: Which week the cycle starts on, for anything that is not weekly.
    #:
    #: Without it every fortnightly meeting would be pinned to the odd weeks of
    #: term, because the whole timetable shares one start date -- and labs
    #: commonly begin in week two. Meaningless when the interval is 1, since
    #: every week is an on-week.
    first_on: date | None = None

    @model_validator(mode="after")
    def validate_meeting(self):
        """Check the times, the kind, and that `first_on` falls on a meeting day.

        Returns:
            The validated model.

        Raises:
            ValueError: If `end_time` is not after `start_time`, `kind` is not a class
                kind, or `first_on` falls on a weekday outside `days`.
        """
        if self.end_time <= self.start_time:
            raise ValueError("A class cannot end before it starts")
        if self.kind not in CLASS_KINDS:
            allowed = ", ".join(kind.value for kind in CLASS_KINDS)
            raise ValueError(f"A class meeting must be one of: {allowed}")

        if self.first_on is not None:
            # Anchoring to a day the meeting does not run on leaves the first
            # cycle looking short -- the engine would skip forward to the next
            # day that does run, and the student would count a week wrong.
            code = WEEKDAY_CODES[self.first_on.weekday()]
            if code not in {day.value for day in self.days}:
                running = ", ".join(day.value for day in self.days)
                raise ValueError(
                    f"The first meeting must fall on a day it runs: {running}"
                )

        return self


class ClassScheduleCreate(BaseModel):
    """Request body that replaces a course's whole timetable.

    Submitting it again replaces the class blocks rather than adding to them; an
    empty `meetings` list removes the timetable.

    Attributes:
        meetings: The timetable's repeating blocks.
        starts_on: First date of the term; None uses the course's start date.
        ends_on: Last date of the term, inclusive; None uses the course's end date.
    """

    meetings: list[ClassMeeting] = Field(default_factory=list)
    #: Default to the course's own dates; overridable for a course whose term
    #: dates are not filled in.
    starts_on: date | None = None
    ends_on: date | None = None

    @model_validator(mode="after")
    def validate_schedule(self):
        """Reject a term that ends before it starts, when both dates are given.

        Returns:
            The validated model.

        Raises:
            ValueError: If `ends_on` is before `starts_on`.
        """
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("A term cannot end before it starts")

        return self


# Kept honest against the engine: the enums above are what the API accepts, and
# the engine is what has to understand them.
assert {frequency.value for frequency in Frequency} == set(FREQUENCIES)
assert {day.value for day in Weekday} == set(WEEKDAY_CODES)
