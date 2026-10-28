"""In-app survey routes under `/api/survey`: what to ask now, and answers."""

from fastapi import APIRouter, HTTPException, Response, status

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Survey.schemas.survey import Pending, ResponseCreate
from app.Survey.services.survey_service import AlreadyAnswered, pending, respond

router = APIRouter()


@router.get("/{user_id}/pending", response_model=Pending)
def get_pending(user_id: VerifiedUserId, db: DBSession):
    """Return the question to ask now, if any: once, after a week of use.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        `question`, or null when there is nothing to ask.
    """
    return Pending(question=pending(db, user_id))


@router.post("/{user_id}/responses", status_code=status.HTTP_204_NO_CONTENT)
def add_response(user_id: VerifiedUserId, response: ResponseCreate, db: DBSession):
    """Record the answer to a survey question; each question is answered once.

    Args:
        user_id: The verified caller's id.
        response: The question and the answer.
        db: Request-scoped database session.

    Returns:
        204 No Content.

    Raises:
        HTTPException: 409 when the question was already answered.
    """
    try:
        respond(db, user_id, response.question, response.answer)
    except AlreadyAnswered:
        raise HTTPException(status_code=409, detail="Already answered")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
