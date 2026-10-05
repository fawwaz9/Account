"""Kept syllabi: storing, finding, serving and deleting the original files.

Phase 1 D24 (account-vision.md §13.20: shared documents are kept as
provenance). Separate from syllabus_service so account deletion can reach it
without importing the whole grades stack. Every function starts from a
`syllabus_parses` row read as the user; the object is named from that row,
never from a request.
"""

import logging
import uuid

from sqlalchemy.orm import Session

from app._database.models import SyllabusParseModel
from app.Intake.services import storage


def keep_file(db: Session, row: SyllabusParseModel, content: bytes) -> None:
    """Keep the original as provenance (§13.20), when a bucket is configured.

    The row is committed first and the object named after it, so no file is
    ever stored that no row can find: whatever happens after the upload, the
    row is what deleting the account walks. A failed upload is logged and the
    parse stands -- the extraction is what the app runs on.
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
    """The kept syllabi behind one of this person's courses, newest first."""
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
    """A kept syllabus, if it is this person's. The object is named from the
    row read here, never from the request."""
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
    """Delete every syllabus this person ever uploaded, before their rows go.

    Every parse row, not only those marked kept: an upload that succeeded just
    before a failed commit left an object the row never recorded, and it is
    named after the row all the same. "Not there" counts as deleted, so this
    is safe to repeat. Raises StorageError if anything could not be deleted --
    the caller must then keep the rows, or the files would outlive the only
    record of them.
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
