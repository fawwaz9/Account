from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Jobs.schemas.job import (
    Job,
    JobCreate,
    JobUpdate,
    ShiftOccurrence,
    ShiftRecord,
    ShiftRecordUpsert,
    ShiftScheduleCreate,
)
from app.Jobs.services.job_service import (
    confirm_shift,
    create_job,
    delete_job,
    get_job,
    list_jobs,
    list_shifts,
    set_shift_schedule,
    update_job,
)
from app.shared import audit
from app.shared.errors import error_user, responses

router = APIRouter()

JOB_404 = {404: {"description": "Job not found"}}
JOB_BOTH = {**JOB_404, 400: {"description": "Invalid job data"}}


@router.get("/{user_id}/jobs", response_model=list[Job], responses=responses["user_404"])
def get_jobs(
    user_id: VerifiedUserId,
    db: DBSession,
    include_archived: bool = Query(
        default=False, description="Also return jobs that have been archived"
    ),
):
    """Every job, current ones first. A job you have left keeps its history."""
    jobs = list_jobs(db, user_id, include_archived)
    if jobs is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return jobs


@router.post("/{user_id}/jobs", response_model=Job, responses=responses["user_both"])
def add_job(user_id: VerifiedUserId, job: JobCreate, db: DBSession):
    created = create_job(db, user_id, job)
    if created is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return created


# Declared above /jobs/{job_id}: FastAPI matches in declaration order, so below
# it "shifts" is parsed as a job id and the request fails as a bad UUID.
@router.get(
    "/{user_id}/jobs/shifts",
    response_model=list[ShiftOccurrence],
    responses=responses["user_404"],
)
def get_shifts(
    user_id: VerifiedUserId,
    db: DBSession,
    start: date = Query(..., description="First date of the window, inclusive"),
    end: date = Query(..., description="Last date of the window, inclusive"),
):
    """Every shift date in the window, with what is known about each.

    A past shift nobody has confirmed is returned with its scheduled hours and
    `assumed` set, rather than left out: forgetting the admin should not make a
    fortnight of work read as an idle one.
    """
    shifts = list_shifts(db, user_id, start, end)
    if shifts is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return shifts


@router.put(
    "/{user_id}/jobs/shifts/{event_id}/{on_date}",
    response_model=ShiftRecord,
    responses=JOB_BOTH,
)
def record_shift(
    user_id: VerifiedUserId,
    event_id: UUID,
    on_date: date,
    record: ShiftRecordUpsert,
    db: DBSession,
):
    """Confirm what was actually worked on one date of a shift.

    A PUT because `(event_id, on_date)` names the thing being written, and
    confirming the same Friday twice must leave one answer rather than two.
    """
    try:
        saved = confirm_shift(db, user_id, event_id, on_date, record)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if saved is None:
        raise HTTPException(status_code=404, detail="Shift not found")

    return saved


@router.get("/{user_id}/jobs/{job_id}", response_model=Job, responses=JOB_404)
def get_single_job(user_id: VerifiedUserId, job_id: UUID, db: DBSession):
    job = get_job(db, user_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return job


@router.patch("/{user_id}/jobs/{job_id}", response_model=Job, responses=JOB_BOTH)
def edit_job(user_id: VerifiedUserId, job_id: UUID, job: JobUpdate, db: DBSession):
    try:
        updated = update_job(db, user_id, job_id, job)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return updated


@router.delete("/{user_id}/jobs/{job_id}", response_model=Job, responses=JOB_404)
def remove_job(user_id: VerifiedUserId, job_id: UUID, db: DBSession):
    """Remove a job entered by mistake, and the calendar blocks it put up.

    Ending a job is `ended_on` and hiding one is `archived`; both keep the
    history. This does not.
    """
    deleted = delete_job(db, user_id, job_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Job not found")

    audit.deletion("job", user_id=user_id, target_id=job_id, detail=deleted.name)
    return deleted


@router.put(
    "/{user_id}/jobs/{job_id}/schedule",
    response_model=list[UUID],
    responses=JOB_BOTH,
)
def put_shift_schedule(
    user_id: VerifiedUserId,
    job_id: UUID,
    schedule: ShiftScheduleCreate,
    db: DBSession,
):
    """Replace this job's recurring shifts with the pattern given."""
    try:
        created = set_shift_schedule(db, user_id, job_id, schedule)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return created
