from fastapi import APIRouter, Response, status

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Usage.schemas.usage import VisitCreate
from app.Usage.services.usage_service import PROMPTED_VISIT, VISIT, record

router = APIRouter()


@router.post("/{user_id}/visits", status_code=status.HTTP_204_NO_CONTENT)
def add_visit(user_id: VerifiedUserId, visit: VisitCreate, db: DBSession):
    """Count today's visit to a module. Answers 204 whatever happens to the count."""
    record(db, user_id, PROMPTED_VISIT if visit.prompted else VISIT, visit.module.value)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
