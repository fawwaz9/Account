"""Kept syllabus files: storing, listing, serving and deleting the originals.

Separate from `syllabus_service` so account deletion can reach it without the grades
stack. Every function starts from a `syllabus_parses` row read as the user, and the
object is named from that row, never from a request.
"""

import logging
import uuid

from sqlalchemy.orm import Session

from app._database.models import SyllabusParseModel
from app.Intake.services import storage


def keep_file(db: Session, row: SyllabusParseModel, content: bytes) -> None:
    """Store a parse's original file in the bucket, when one is configured.

    Args:
        db: Open session; the row must already be committed.
        row: The committed parse row, which names the object.
        content: The file's bytes.

    Note:
        Commits `file_kept = True` after a successful upload. A failed upload is logged
        and the parse stands, since the extraction is what the app runs on.
    """
    if not storage.configured():
        return
    try:
        storage.put(row.object_name, content, row.media_type)
    except storage.StorageError as exc:
        logging.getLogger(__name__).warning("syllabus %s not kept: %s", row.id, exc)
        return
    row.file_kept = True
    db.commit()


def kept_files(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> list[SyllabusParseModel]:
    """Return the kept syllabi behind one of the user's courses, newest first.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        course_id: The course.

    Returns:
        The parse rows with a kept file; empty when there are none.
    """
    return (
        db.query(SyllabusParseModel)
        .filter(
            SyllabusParseModel.user_id == user_id,
            SyllabusParseModel.course_id == course_id,
            SyllabusParseModel.file_kept.is_(True),
        )
        .order_by(SyllabusParseModel.created_at.desc())
        .all()
    )


def read_kept_file(db: Session, user_id: uuid.UUID, parse_id: uuid.UUID) -> tuple[SyllabusParseModel, bytes] | None:
    """Return a kept syllabus row and its bytes, if it is the user's.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        parse_id: The parse whose file to read.

    Returns:
        (row, file bytes), or None when there is no kept file of the user's with that
        id.

    Raises:
        StorageError: If the bucket refuses or cannot be reached.
    """
    row = (
        db.query(SyllabusParseModel)
        .filter(
            SyllabusParseModel.id == parse_id,
            SyllabusParseModel.user_id == user_id,
            SyllabusParseModel.file_kept.is_(True),
        )
        .first()
    )
    if row is None:
        return None
    return row, storage.get(row.object_name)


def discard_files(db: Session, user_id: uuid.UUID) -> int:
    """Delete every file the user ever uploaded, before their parse rows are deleted.

    Every parse row is tried, not only those marked kept, since an upload can succeed
    just before a failed commit.

    Args:
        db: Open session acting as the user.
        user_id: Whose files to delete.

    Returns:
        How many objects were deleted or found already gone; 0 with no rows.

    Raises:
        NotConfigured: If files were kept but no bucket is configured now.
        StorageError: If any delete fails; the caller must then keep the rows, or the
            files would outlive their only record.
    """
    rows = db.query(SyllabusParseModel).filter(SyllabusParseModel.user_id == user_id).all()
    if not rows:
        return 0
    if not storage.configured():
        if any(row.file_kept for row in rows):
            raise storage.NotConfigured
        return 0
    for row in rows:
        storage.delete(row.object_name)
    return len(rows)
