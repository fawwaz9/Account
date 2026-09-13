"""A course's timetable, as events.

The first consumer of the recurrence engine, and deliberately so: class times
are the case where a repeat is obviously right, which makes them the place to
prove the engine before recurring payments and repeating tasks depend on it too.

There is no `classes` table. A lecture is an event with a `course_id` and a
weekly rule, which is what it actually is -- and it means the calendar needs no
second code path to draw one.
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
    """The course's existing timetable blocks, or None if no such course."""
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
    """When the timetable runs, preferring what the form said over the course.

    Courses already carry start and end dates, so in the ordinary case the form
    needs no date fields at all -- which is the whole point of generating a
    timetable from a course rather than asking for one.
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
    return f"{course.code} {MEETING_LABELS.get(meeting.kind, 'Class')}"


def check_anchors(data: ClassScheduleCreate, starts_on: date, ends_on: date | None) -> None:
    """A first meeting outside the term is a typo, and would draw nothing.

    Checked here rather than on the schema because only this function knows the
    term's dates -- they come from the course when the form leaves them out.
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
    """Replace the course's timetable with the meetings given.

    Replace rather than append: this is one form describing one timetable, and
    submitting it a second time after fixing a room number must not leave the
    old room on the calendar beside the new one. Only the course's own class
    blocks are touched -- a midterm or a personal event attached to the same
    course survives.
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
