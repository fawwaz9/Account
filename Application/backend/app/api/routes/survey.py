from fastapi import APIRouter, HTTPException, Response, status

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Survey.schemas.survey import Pending, ResponseCreate
from app.Survey.services.survey_service import AlreadyAnswered, pending, respond

router = APIRouter()


@router.get("/{user_id}/pending", response_model=Pending)
def get_pending(user_id: VerifiedUserId, db: DBSession):
    """The question to ask now, if any. Asked once, of people with an opinion."""
    return Pending(question=pending(db, user_id))


@router.post("/{user_id}/responses", status_code=status.HTTP_204_NO_CONTENT)
def add_response(user_id: VerifiedUserId, response: ResponseCreate, db: DBSession):
    try:
        respond(db, user_id, response.question, response.answer)
    except AlreadyAnswered:
        raise HTTPException(status_code=409, detail="Already answered")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
