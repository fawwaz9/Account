"""In-app questions, asked once. Phase 1 item 13.

The Phase 1 exit gate counts people who would be "very disappointed" without
the app (account-vision.md §11), which nobody can read without asking. So the
app asks -- once, of people who have used it enough to have an opinion, and
never again after an answer or a "don't ask again". The answers are counted by
the owner-run usage report and read nowhere else.
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
    pass


def days_used(db: Session, user_id: uuid.UUID) -> int:
    return (
        db.query(func.count(func.distinct(UsageEventModel.day)))
        .filter(UsageEventModel.user_id == user_id)
        .scalar()
    ) or 0


def answered(db: Session, user_id: uuid.UUID, question: Question) -> bool:
    return (
        db.query(SurveyResponseModel.id)
        .filter(SurveyResponseModel.user_id == user_id, SurveyResponseModel.question == question.value)
        .first()
        is not None
    )


def pending(db: Session, user_id: uuid.UUID) -> Question | None:
    question = Question.DISAPPOINTMENT
    if answered(db, user_id, question):
        return None
    return question if days_used(db, user_id) >= ELIGIBLE_DAYS else None


def respond(db: Session, user_id: uuid.UUID, question: Question, answer: Answer) -> None:
    """Record the answer. A second answer to the same question is refused, not merged."""
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
