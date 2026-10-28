"""Syllabus intake routes under `/api/intake`: read, apply, add, kept files."""

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
    """Return whether syllabus reading is set up on this server.

    Args:
        user_id: The verified caller's id.

    Returns:
        `available`, False until a provider, model and key are configured.
    """
    return IntakeStatus(available=llm.configured())


@router.post("/{user_id}/syllabus", response_model=ParseResult)
def read_syllabus(user_id: VerifiedUserId, upload: SyllabusUpload, db: DBSession):
    """Read an uploaded syllabus into assessments to check; builds nothing.

    Args:
        user_id: The verified caller's id.
        upload: The file, base64-encoded, with its name and type.
        db: Request-scoped database session.

    Returns:
        The parse, with warnings to check before confirming.

    Raises:
        HTTPException: 503 when syllabus reading is not set up; 429 when today's parses
            are used up; 502 when the model provider fails; 400 for a bad file or an
            answer that fails the extract schema.
    """
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
    """Build a new course from what the student confirmed on the check screen.

    Counted as a create in Grades.

    Args:
        user_id: The verified caller's id.
        parse_id: The parse being applied.
        confirmed: The course and assessments as confirmed.
        db: Request-scoped database session.

    Returns:
        The new course's id, grades created and the no-change measure.

    Raises:
        HTTPException: 400 when the parse was already applied, the term is missing or
            unknown, the weights do not sum to 100, or the code exists; 404 when the
            parse is missing or another user's.
    """
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
    """Return what a syllabus would add to an existing course; writes nothing.

    Args:
        user_id: The verified caller's id.
        parse_id: The parse.
        course_id: The course.
        db: Request-scoped database session.

    Returns:
        The implied rows and whether each exists, weight differences and offers.

    Raises:
        HTTPException: 404 when the parse or course is missing or another user's.
    """
    result = preview_add(db, user_id, parse_id, course_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Parse or course not found")
    return result


@router.post("/{user_id}/syllabus/{parse_id}/add-to/{course_id}", response_model=AddResult)
def add_syllabus_to_course(user_id: VerifiedUserId, parse_id: UUID, course_id: UUID, request: AddRequest, db: DBSession):
    """Add the confirmed assessments an existing course lacks, changing nothing.

    Counted as a create in Grades.

    Args:
        user_id: The verified caller's id.
        parse_id: The parse.
        course_id: The course.
        request: The rows, section choice and rules confirmed.
        db: Request-scoped database session.

    Returns:
        How many rows were added and skipped, and what else was set.

    Raises:
        HTTPException: 400 when the parse was already used; 404 when the parse or course
            is missing or another user's.
    """
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
    """List the syllabus files kept behind a course, newest first.

    Args:
        user_id: The verified caller's id.
        course_id: The course.
        db: Request-scoped database session.

    Returns:
        The kept files; empty when none were kept or the course is not the caller's.
    """
    return kept_files(db, user_id, course_id)


@router.get("/{user_id}/syllabus/{parse_id}/file")
def syllabus_file(user_id: VerifiedUserId, parse_id: UUID, db: DBSession):
    """Download a kept syllabus file, always as an attachment, never rendered inline.

    Args:
        user_id: The verified caller's id.
        parse_id: The parse whose file to fetch.
        db: Request-scoped database session.

    Returns:
        The file, with its stored type, a sanitised file name and `nosniff`.

    Raises:
        HTTPException: 404 when there is no kept file of the caller's with that id; 502
            when storage cannot provide it.
    """
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
    """Return the file name reduced to safe header characters, or "syllabus".

    Args:
        filename: The stored original file name; may be None.

    Returns:
        At most 100 characters of letters, digits, "._ -" and underscores.
    """
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", filename or "")[:100].strip()
    return cleaned or "syllabus"

