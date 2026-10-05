from uuid import UUID

from fastapi import APIRouter, HTTPException

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Intake.schemas.syllabus import ApplyRequest, ApplyResult, IntakeStatus, ParseResult, SyllabusUpload
from app.Intake.services import llm
from app.Intake.services.syllabus_service import RateLimited, apply, parse
from app.Usage.services.usage_service import CREATE, record as record_usage

router = APIRouter()


@router.get("/{user_id}/status", response_model=IntakeStatus)
def intake_status(user_id: VerifiedUserId):
    """Whether syllabus reading is set up on this server."""
    return IntakeStatus(available=llm.configured())


@router.post("/{user_id}/syllabus", response_model=ParseResult)
def read_syllabus(user_id: VerifiedUserId, upload: SyllabusUpload, db: DBSession):
    """Read a syllabus into assessments, weights and dates, to check. Builds nothing."""
    try:
        return parse(db, user_id, upload)
    except llm.NotConfigured:
        raise HTTPException(status_code=503, detail="Syllabus reading isn't set up on the server yet")
    except RateLimited:
        raise HTTPException(status_code=429, detail="That's today's limit for reading syllabi. Try again tomorrow.")
    except llm.ProviderError as exc:
        raise HTTPException(status_code=502, detail=f"Couldn't read the syllabus: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{user_id}/syllabus/{parse_id}/apply", response_model=ApplyResult)
def apply_syllabus(user_id: VerifiedUserId, parse_id: UUID, confirmed: ApplyRequest, db: DBSession):
    """Build the course from what the person confirmed on the verification screen."""
    try:
        result = apply(db, user_id, parse_id, confirmed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Parse not found")
    record_usage(db, user_id, CREATE, "grades")
    return result
