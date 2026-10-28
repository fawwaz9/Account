"""Degree audit routes under `/api/degree`: the audit, requirements and equivalences."""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Grades.schemas.degree import DegreeAudit, Equivalence, EquivalenceWrite, Requirement, RequirementWrite
from app.Grades.services import degree_service
from app.Usage.services.usage_service import CREATE, record as record_usage

router = APIRouter()


@router.get("/{user_id}", response_model=DegreeAudit)
def get_audit(user_id: VerifiedUserId, db: DBSession):
    """Return the degree audit: each requirement against the student's courses.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The audit.

    Raises:
        HTTPException: 404 when the user does not exist.
    """
    result = degree_service.audit(db, user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="User not found")
    return result


@router.post("/{user_id}/requirements", response_model=Requirement)
def add_requirement(user_id: VerifiedUserId, data: RequirementWrite, db: DBSession):
    """Add a degree requirement, and count it as a create in Grades.

    Args:
        user_id: The verified caller's id.
        data: The requirement.
        db: Request-scoped database session.

    Returns:
        The stored requirement.
    """
    result = degree_service.create_requirement(db, user_id, data)
    record_usage(db, user_id, CREATE, "grades")
    return result


@router.put("/{user_id}/requirements/{requirement_id}", response_model=Requirement)
def edit_requirement(user_id: VerifiedUserId, requirement_id: UUID, data: RequirementWrite, db: DBSession):
    """Replace a degree requirement.

    Args:
        user_id: The verified caller's id.
        requirement_id: The requirement.
        data: Its new fields.
        db: Request-scoped database session.

    Returns:
        The updated requirement.

    Raises:
        HTTPException: 404 when the requirement is missing or another user's.
    """
    result = degree_service.update_requirement(db, user_id, requirement_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return result


@router.delete("/{user_id}/requirements/{requirement_id}")
def remove_requirement(user_id: VerifiedUserId, requirement_id: UUID, db: DBSession):
    """Delete a degree requirement.

    Args:
        user_id: The verified caller's id.
        requirement_id: The requirement.
        db: Request-scoped database session.

    Returns:
        `{"deleted": true}`.

    Raises:
        HTTPException: 404 when the requirement is missing or another user's.
    """
    if not degree_service.delete_requirement(db, user_id, requirement_id):
        raise HTTPException(status_code=404, detail="Requirement not found")
    return {"deleted": True}


@router.post("/{user_id}/equivalences", response_model=Equivalence)
def add_equivalence(user_id: VerifiedUserId, data: EquivalenceWrite, db: DBSession):
    """Add a course equivalence, and count it as a create in Grades.

    Args:
        user_id: The verified caller's id.
        data: The equivalence.
        db: Request-scoped database session.

    Returns:
        The stored equivalence.
    """
    result = degree_service.create_equivalence(db, user_id, data)
    record_usage(db, user_id, CREATE, "grades")
    return result


@router.put("/{user_id}/equivalences/{equivalence_id}", response_model=Equivalence)
def edit_equivalence(user_id: VerifiedUserId, equivalence_id: UUID, data: EquivalenceWrite, db: DBSession):
    """Replace a course equivalence.

    Args:
        user_id: The verified caller's id.
        equivalence_id: The equivalence.
        data: Its new fields.
        db: Request-scoped database session.

    Returns:
        The updated equivalence.

    Raises:
        HTTPException: 404 when the equivalence is missing or another user's.
    """
    result = degree_service.update_equivalence(db, user_id, equivalence_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="Equivalence not found")
    return result


@router.delete("/{user_id}/equivalences/{equivalence_id}")
def remove_equivalence(user_id: VerifiedUserId, equivalence_id: UUID, db: DBSession):
    """Delete a course equivalence.

    Args:
        user_id: The verified caller's id.
        equivalence_id: The equivalence.
        db: Request-scoped database session.

    Returns:
        `{"deleted": true}`.

    Raises:
        HTTPException: 404 when the equivalence is missing or another user's.
    """
    if not degree_service.delete_equivalence(db, user_id, equivalence_id):
        raise HTTPException(status_code=404, detail="Equivalence not found")
    return {"deleted": True}
