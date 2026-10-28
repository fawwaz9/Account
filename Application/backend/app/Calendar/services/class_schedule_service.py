"""Service functions for a course's timetable, stored as repeating calendar events.

There is no classes table: a lecture is an event with a `course_id`, a class
kind and a weekly rule, so the calendar draws it with no second code path.
"""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app._database.models import EventModel
from app.Calendar.schemas.event import (
    CLASS_KINDS,
    ClassMeeting,
    ClassScheduleCreate,
    EventKind,
)
from app.Calendar.services.event_service import attach_recurrence, owned_course
from app.Calendar.utils.recurrence import WEEKLY, format_byday

CLASS_KIND_VALUES = {kind.value for kind in CLASS_KINDS}

#: What a block is called on the calendar, per kind.
MEETING_LABELS = {
    EventKind.LECTURE: "Lecture",
    EventKind.LAB: "Lab",
    EventKind.DISCUSSION: "Discussion",
}


def get_class_schedule(db: Session, user_id: uuid.UUID, course_id: uuid.UUID):
    """Return a course's class events (lectures, labs, discussions), by start time.

    Args:
        db: Open database session.
        user_id: Whose course.
        course_id: The course.

    Returns:
        The event rows with recurrence attached; None when the course is not the
        user's.
    """
    if owned_course(db, user_id, course_id) is None:
        return None

    events = (
        db.query(EventModel)
        .filter(
            EventModel.user_id == user_id,
            EventModel.course_id == course_id,
            EventModel.kind.in_(CLASS_KIND_VALUES),
        )
        .order_by(EventModel.start_time)
        .all()
    )
    return [attach_recurrence(event) for event in events]


def term_window(course, data: ClassScheduleCreate) -> tuple[date, date]:
    """Return the dates a timetable runs, preferring the form's dates over the course's.

    Args:
        course: The course row, whose start and end dates are the fallback.
        data: The timetable form.

    Returns:
        The first and last dates, inclusive.

    Raises:
        ValueError: If neither the form nor the course gives both dates, or the
            term ends before it starts.
    """
    starts_on = data.starts_on or course.start_date
    ends_on = data.ends_on or course.end_date

    if starts_on is None or ends_on is None:
        raise ValueError(
            "This course has no start and end date, so give the term dates here"
        )

    if ends_on < starts_on:
        raise ValueError("A term cannot end before it starts")

    return starts_on, ends_on


def meeting_title(course, meeting: ClassMeeting) -> str:
    """Return a class block's calendar title, such as "CPSC 221 Lab".

    Args:
        course: The course the timetable belongs to.
        meeting: One meeting of the timetable.

    Returns:
        The course code followed by the meeting's kind label.
    """
    return f"{course.code} {MEETING_LABELS.get(meeting.kind, 'Class')}"


def check_anchors(data: ClassScheduleCreate, starts_on: date, ends_on: date | None) -> None:
    """Refuse a non-weekly meeting whose first date falls outside the term.

    Args:
        data: The timetable form.
        starts_on: The term's first date.
        ends_on: The term's last date; None leaves the end unchecked.

    Raises:
        ValueError: If a `first_on` falls before the term starts or after it ends.
    """
    for meeting in data.meetings:
        if meeting.first_on is None or meeting.interval == 1:
            continue
        if meeting.first_on < starts_on:
            raise ValueError("A first meeting cannot fall before the term starts")
        if ends_on is not None and meeting.first_on > ends_on:
            raise ValueError("A first meeting cannot fall after the term ends")


def set_class_schedule(
    db: Session,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    data: ClassScheduleCreate,
):
    """Replace a course's timetable with the meetings given.

    Deletes every existing lecture, lab and discussion event of the course and
    writes one weekly event per meeting, ending on the term's last date; other
    events of the course (an exam, a personal block) are untouched. Commits.

    Args:
        db: Open database session.
        user_id: Whose course.
        course_id: The course.
        data: The meetings and, optionally, the term dates.

    Returns:
        The new event rows with recurrence attached; None when the course is not
        the user's.

    Raises:
        ValueError: If the term dates are missing or inverted, or a first meeting
            falls outside the term.

    Note:
        Replacing deletes the old events outright, so dates cancelled on them
        (`skipped_dates`) and any members are not carried over.
    """
    course = owned_course(db, user_id, course_id)
    if course is None:
        return None

    starts_on, ends_on = term_window(course, data)
    check_anchors(data, starts_on, ends_on)

    existing = (
        db.query(EventModel)
        .filter(
            EventModel.user_id == user_id,
            EventModel.course_id == course_id,
            EventModel.kind.in_(CLASS_KIND_VALUES),
        )
        .all()
    )
    for event in existing:
        db.delete(event)
    db.flush()

    created: list[EventModel] = []
    for meeting in data.meetings:
        # The interval says how often; `first_on` says which week the cycle
        # starts on, and both are needed. Anchoring every meeting to the term
        # start would pin each fortnightly one to the odd weeks of term, and a
        # lab that begins in week two -- the common case -- would be a week out
        # for the whole term while looking perfectly scheduled.
        #
        # For a weekly meeting there is no phase to choose, so the term start is
        # right and `first_on` is ignored.
        anchor = starts_on
        if meeting.interval > 1 and meeting.first_on is not None:
            anchor = meeting.first_on

        event = EventModel(
            id=uuid.uuid4(),
            user_id=user_id,
            course_id=course_id,
            title=meeting_title(course, meeting),
            kind=meeting.kind.value,
            location=meeting.location,
            starts_on=anchor,
            start_time=meeting.start_time,
            end_time=meeting.end_time,
            recur_freq=WEEKLY,
            recur_interval=meeting.interval,
            recur_byday=format_byday(day.value for day in meeting.days),
            # Bounded by the term, so a course that ends in December stops
            # drawing lectures in January without anyone having to remember to
            # delete it.
            recur_until=ends_on,
            recur_count=None,
            skipped_dates=[],
        )
        db.add(event)
        created.append(event)

    db.commit()
    for event in created:
        db.refresh(event)

    return [attach_recurrence(event) for event in created]
