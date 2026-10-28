"""Job application routes, under /api/jobs/{user_id}/applications.

Single-user: another person's application or season answers 404, the same as a
missing one, except the co-op pay figures (Phase 3 item 12), which are shared
aggregates read through their floor. The literal `/stats`, `/seasons` and
`/salaries` paths are declared above `/{application_id}`, which would otherwise
parse them as ids.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Jobs.schemas.application import (
    Application, ApplicationIn, ApplicationStats, ApplicationUpdate, SalaryFigure, SalaryShareIn, Season, SeasonIn,
    StepIn,
)
from app.Jobs.services import application_service as service
from app.shared.errors import error_user, responses
from app.Usage.services.usage_service import CREATE, record as record_usage

router = APIRouter()

NOT_FOUND = "Application not found"
NO_SEASON = "Season not found"
SEASON_404 = {404: {"description": NO_SEASON}}
APP_404 = {404: {"description": NOT_FOUND}, 400: {"description": "Not allowed for this application"}}


@router.get("/{user_id}/applications", response_model=list[Application], responses=SEASON_404)
def list_applications(user_id: VerifiedUserId, db: DBSession, season_id: UUID | None = None):
    """List the caller's applications, or those applied for within one season's months.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        season_id: Only applications whose applied date falls in this season; omit
            for all.

    Returns:
        The applications, newest applied first, each with its history.

    Raises:
        HTTPException: 404 if the season is not the caller's or the user does not
            exist.
    """
    try:
        found = service.list_applications(db, user_id, season_id)
    except service.NoSuchSeason as exc:
        raise HTTPException(status_code=404, detail=NO_SEASON) from exc
    if found is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return found


@router.post("/{user_id}/applications", response_model=Application, responses=responses["user_404"])
def create_application(user_id: VerifiedUserId, body: ApplicationIn, db: DBSession):
    """Record a new job application, with its first "applied" step.

    Args:
        user_id: The verified caller's id.
        body: The application.
        db: Request-scoped database session.

    Returns:
        The created application.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    made = service.create(db, user_id, body)
    if made is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    record_usage(db, user_id, CREATE, "jobs")
    return made


@router.get("/{user_id}/applications/stats", response_model=ApplicationStats, responses=SEASON_404)
def application_stats(user_id: VerifiedUserId, db: DBSession, season_id: UUID | None = None):
    """Get reply, interview and offer figures and the Sankey flows for the caller.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        season_id: Only applications within this season; omit for all.

    Returns:
        The figures, read from each application's history.

    Raises:
        HTTPException: 404 if the season is not the caller's or the user does not
            exist.
    """
    try:
        found = service.stats(db, user_id, season_id)
    except service.NoSuchSeason as exc:
        raise HTTPException(status_code=404, detail=NO_SEASON) from exc
    if found is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return found


# --- seasons (D7). Literal paths, declared above /{application_id}. ----------

@router.get("/{user_id}/applications/seasons", response_model=list[Season], responses=responses["user_404"])
def list_seasons(user_id: VerifiedUserId, db: DBSession):
    """List the caller's recruiting seasons, latest start first.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The seasons.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    found = service.list_seasons(db, user_id)
    if found is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return found


@router.post("/{user_id}/applications/seasons", response_model=Season, responses=responses["user_404"])
def create_season(user_id: VerifiedUserId, body: SeasonIn, db: DBSession):
    """Create a recruiting season: a name and a range of months.

    Args:
        user_id: The verified caller's id.
        body: The name and the first and last months, as YYYY-MM.
        db: Request-scoped database session.

    Returns:
        The created season.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    made = service.create_season(db, user_id, body)
    if made is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return made


@router.put("/{user_id}/applications/seasons/{season_id}", response_model=Season, responses=SEASON_404)
def update_season(user_id: VerifiedUserId, season_id: UUID, body: SeasonIn, db: DBSession):
    """Replace one of the caller's seasons' name and months.

    Args:
        user_id: The verified caller's id.
        season_id: The season.
        body: The new name and months.
        db: Request-scoped database session.

    Returns:
        The updated season.

    Raises:
        HTTPException: 404 if the season is missing or not the caller's.
    """
    found = service.update_season(db, user_id, season_id, body)
    if found is None:
        raise HTTPException(status_code=404, detail=NO_SEASON)
    return found


@router.delete("/{user_id}/applications/seasons/{season_id}", responses=SEASON_404)
def delete_season(user_id: VerifiedUserId, season_id: UUID, db: DBSession):
    """Delete one of the caller's seasons; its applications are untouched.

    Args:
        user_id: The verified caller's id.
        season_id: The season.
        db: Request-scoped database session.

    Returns:
        `{"deleted": true}`.

    Raises:
        HTTPException: 404 if the season is missing or not the caller's.
    """
    if service.delete_season(db, user_id, season_id) is None:
        raise HTTPException(status_code=404, detail=NO_SEASON)
    return {"deleted": True}


@router.get("/{user_id}/applications/salaries", response_model=list[SalaryFigure])
def list_salaries(user_id: VerifiedUserId, db: DBSession):
    """List typical co-op pay per employer, from offers students chose to share.

    Each employer appears once 5 verified offers have been shared, counted in whole
    batches of 5, with no names (Phase 3 item 12, D11, D12).

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        Each employer's median and middle half in dollars per hour, by name.
    """
    return service.salary_figures(db)


@router.patch("/{user_id}/applications/{application_id}", response_model=Application, responses=APP_404)
def update_application(user_id: VerifiedUserId, application_id: UUID, body: ApplicationUpdate, db: DBSession):
    """Change the fields sent on one of the caller's applications.

    Args:
        user_id: The verified caller's id.
        application_id: The application.
        body: The fields to change.
        db: Request-scoped database session.

    Returns:
        The updated application.

    Raises:
        HTTPException: 400 if company or role would be blank, only half of the
            offer's pay would be set, or a later step is dated before the new
            applied date; 404 if the application is missing or not the caller's.
    """
    try:
        found = service.update(db, user_id, application_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if found is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return found


@router.delete("/{user_id}/applications/{application_id}", responses=APP_404)
def delete_application(user_id: VerifiedUserId, application_id: UUID, db: DBSession):
    """Delete one of the caller's applications and its history.

    Args:
        user_id: The verified caller's id.
        application_id: The application.
        db: Request-scoped database session.

    Returns:
        `{"deleted": true}`.

    Raises:
        HTTPException: 404 if the application is missing or not the caller's.
    """
    if service.delete(db, user_id, application_id) is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return {"deleted": True}


@router.post("/{user_id}/applications/{application_id}/steps", response_model=Application, responses=APP_404)
def add_step(user_id: VerifiedUserId, application_id: UUID, body: StepIn, db: DBSession):
    """Record a status change on one of the caller's applications.

    Args:
        user_id: The verified caller's id.
        application_id: The application.
        body: The new status, its date and an optional note.
        db: Request-scoped database session.

    Returns:
        The application, with its status now the latest step's.

    Raises:
        HTTPException: 400 if the step is dated before the application; 404 if the
            application is missing or not the caller's.
    """
    try:
        found = service.add_step(db, user_id, application_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if found is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return found


@router.delete("/{user_id}/applications/{application_id}/steps/{step_id}", response_model=Application, responses=APP_404)
def delete_step(user_id: VerifiedUserId, application_id: UUID, step_id: UUID, db: DBSession):
    """Take back a status change entered by mistake.

    Args:
        user_id: The verified caller's id.
        application_id: The application.
        step_id: The step.
        db: Request-scoped database session.

    Returns:
        The application, with its status back to the latest remaining step's.

    Raises:
        HTTPException: 400 if the step is the first "applied" step; 404 if the
            application or step is missing or not the caller's.
    """
    try:
        found = service.delete_step(db, user_id, application_id, step_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if found is None:
        raise HTTPException(status_code=404, detail="Step not found")
    return found


@router.put("/{user_id}/applications/{application_id}/salary-share", response_model=Application,
            responses=APP_404)
def set_salary_share(user_id: VerifiedUserId, application_id: UUID, body: SalaryShareIn, db: DBSession):
    """Share an offer's pay, with no name, toward its employer's typical pay; or take it back.

    Args:
        user_id: The verified caller's id.
        application_id: The application.
        body: Whether to share it.
        db: Request-scoped database session.

    Returns:
        The application, with `salary_shared` as now set.

    Raises:
        HTTPException: 400 when sharing an application with no offer pay recorded;
            404 if the application is missing or not the caller's.
    """
    try:
        found = service.set_salary_share(db, user_id, application_id, body.share)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if found is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return found
