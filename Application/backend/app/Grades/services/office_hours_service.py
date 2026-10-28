"""Office-hour check-ins (Phase 3 item 11): the caller's own, and how slots read.

A check-in records the local weekday and hour, in the student's own time zone, and
the key the course is counted under. The daily recount turns everyone's into the
sealed slot counts; nothing here reads another user's rows.
"""
import uuid
from datetime import timedelta

from sqlalchemy.orm import Session

from app._database.aggregates import Slot
from app._database.models import CourseModel, OfficeHourCheckinModel, utc_now
from app.Grades.services.term_review_service import course_key_of
from app.shared.dates import user_now

#: A second tap within this many minutes changes the first check-in instead of
#: adding another, so one visit is one answer.
MERGE_MINUTES = 30


class CheckInError(ValueError):
    """Raised when a check-in can't be counted; the message says why."""
    pass


def check_in(db: Session, user_id: uuid.UUID, course_id: uuid.UUID, wait: str) -> OfficeHourCheckinModel | None:
    """Record that the caller is at a course's office hours, and how the line is.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.
        wait: "none", "short" or "long".

    Returns:
        The check-in (a recent one changed, or a new one); None when the course is
        missing or another user's.

    Raises:
        CheckInError: If the course is transfer credit, or its code can't be counted
            under a course key.

    Note:
        Commits.
    """
    course = db.query(CourseModel).filter(CourseModel.id == course_id, CourseModel.user_id == user_id).first()
    if course is None:
        return None
    if course.transfer_credit:
        raise CheckInError("Transfer credit has no office hours to check in to.")
    key = course_key_of(db, course)
    if key is None:
        raise CheckInError("This course's code isn't a course code, so a check-in couldn't be counted.")
    now = utc_now()
    recent = (
        db.query(OfficeHourCheckinModel)
        .filter(OfficeHourCheckinModel.user_id == user_id, OfficeHourCheckinModel.course_id == course_id,
                OfficeHourCheckinModel.checked_at > now - timedelta(minutes=MERGE_MINUTES))
        .order_by(OfficeHourCheckinModel.checked_at.desc())
        .first()
    )
    if recent is not None:
        recent.wait = wait
        db.commit()
        db.refresh(recent)
        return recent
    local = user_now(db, user_id)
    row = OfficeHourCheckinModel(user_id=user_id, course_id=course_id, course_key=key, weekday=local.weekday(),
                                 hour=local.hour, wait=wait, checked_at=now)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def remove(db: Session, user_id: uuid.UUID, checkin_id: uuid.UUID) -> bool:
    """Delete one of the caller's check-ins, such as one tapped by mistake.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        checkin_id: The check-in.

    Returns:
        True if it was deleted; False when it is missing or another user's.

    Note:
        Commits. The next recount drops it from the slot counts.
    """
    row = db.query(OfficeHourCheckinModel).filter(
        OfficeHourCheckinModel.id == checkin_id, OfficeHourCheckinModel.user_id == user_id).first()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def reading(slot: Slot) -> str:
    """Return how a slot usually is: the answer most people gave, the busier on a tie.

    Args:
        slot: The slot's counts.

    Returns:
        "long", "short" or "none".
    """
    votes = [("long", slot.long_votes), ("short", slot.short_votes), ("none", slot.none_votes)]
    return max(votes, key=lambda pair: pair[1])[0]
