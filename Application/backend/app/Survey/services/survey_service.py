"""The in-app survey: one question, asked once of people who have used the app a week.

Answers, "don't ask again" included, are final and read only by the owner-run usage
report, as counts.
"""
import uuid

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app._database.models import SurveyResponseModel, UsageEventModel
from app.Survey.schemas.survey import Answer, Question

#: Days with any use before the question appears. Asked in week one, "how would
#: you feel without it" has no answer yet.
ELIGIBLE_DAYS = 7


class AlreadyAnswered(Exception):
    """Raised when the user has already answered the question."""
    pass


def days_used(db: Session, user_id: uuid.UUID) -> int:
    """Return on how many distinct days the user has any recorded use.

    Args:
        db: Open database session.
        user_id: Owner of the rows.

    Returns:
        The count of distinct days in `usage_events`; 0 when none.
    """
    return (
        db.query(func.count(func.distinct(UsageEventModel.day)))
        .filter(UsageEventModel.user_id == user_id)
        .scalar()
    ) or 0


def answered(db: Session, user_id: uuid.UUID, question: Question) -> bool:
    """Return whether the user has answered a question, dismissal included.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        question: The survey question.

    Returns:
        True when a response row exists for it.
    """
    return (
        db.query(SurveyResponseModel.id)
        .filter(SurveyResponseModel.user_id == user_id, SurveyResponseModel.question == question.value)
        .first()
        is not None
    )


def pending(db: Session, user_id: uuid.UUID) -> Question | None:
    """Return the question to ask now, or None.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.

    Returns:
        The disappointment question once the user has used the app on `ELIGIBLE_DAYS`
        days and not answered it; otherwise None.
    """
    question = Question.DISAPPOINTMENT
    if answered(db, user_id, question):
        return None
    return question if days_used(db, user_id) >= ELIGIBLE_DAYS else None


def respond(db: Session, user_id: uuid.UUID, question: Question, answer: Answer) -> None:
    """Record the user's answer to a question; a second answer is refused, never merged.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        question: The question answered.
        answer: The answer, "dismissed" meaning never ask again.

    Raises:
        AlreadyAnswered: If the question was answered before, including by a concurrent
            request.

    Note:
        Commits.
    """
    if answered(db, user_id, question):
        raise AlreadyAnswered
    db.add(SurveyResponseModel(
        id=uuid.uuid4(), user_id=user_id, question=question.value, answer=answer.value,
    ))
    try:
        db.commit()
    except IntegrityError as exc:  # two tabs answering at once
        db.rollback()
        raise AlreadyAnswered from exc
