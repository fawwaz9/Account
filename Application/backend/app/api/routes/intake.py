import re
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Intake.schemas.syllabus import (
    AddPreview,
    AddRequest,
    AddResult,
    ApplyRequest,
    ApplyResult,
    IntakeStatus,
    KeptSyllabus,
    ParseResult,
    SyllabusUpload,
)
from app.Intake.services import llm, storage
from app.Intake.services.kept_files import kept_files, read_kept_file
from app.Intake.services.syllabus_service import RateLimited, add_to_course, apply, parse, preview_add
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


@router.get("/{user_id}/syllabus/{parse_id}/add-to/{course_id}", response_model=AddPreview)
def preview_add_to_course(user_id: VerifiedUserId, parse_id: UUID, course_id: UUID, db: DBSession):
    """What a syllabus would add to a course you already have. Writes nothing."""
    result = preview_add(db, user_id, parse_id, course_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Parse or course not found")
    return result


@router.post("/{user_id}/syllabus/{parse_id}/add-to/{course_id}", response_model=AddResult)
def add_syllabus_to_course(user_id: VerifiedUserId, parse_id: UUID, course_id: UUID, request: AddRequest, db: DBSession):
    """Add the confirmed assessments the course lacks. Never changes what it has."""
    try:
        result = add_to_course(db, user_id, parse_id, course_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Parse or course not found")
    record_usage(db, user_id, CREATE, "grades")
    return result


@router.get("/{user_id}/courses/{course_id}/syllabi", response_model=list[KeptSyllabus])
def course_syllabi(user_id: VerifiedUserId, course_id: UUID, db: DBSession):
    """The syllabus files kept behind a course, newest first. Empty when none were kept."""
    return kept_files(db, user_id, course_id)


@router.get("/{user_id}/syllabus/{parse_id}/file")
def syllabus_file(user_id: VerifiedUserId, parse_id: UUID, db: DBSession):
    """The original file, always as a download: never rendered by the API's own origin."""
    try:
        found = read_kept_file(db, user_id, parse_id)
    except storage.StorageError as exc:
        raise HTTPException(status_code=502, detail="Couldn't fetch the file from storage") from exc
    if found is None:
        raise HTTPException(status_code=404, detail="File not found")
    row, content = found
    return Response(
        content=content,
        media_type=row.media_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{download_name(row.filename)}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


def download_name(filename: str | None) -> str:
    """The uploaded name, reduced to characters a header cannot be broken by."""
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", filename or "")[:100].strip()
    return cleaned or "syllabus"

