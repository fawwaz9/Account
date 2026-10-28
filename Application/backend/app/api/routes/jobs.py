"""Job routes under /api/jobs: jobs, shifts, earnings, paycheques and the tax packet.

Each handler parses the request, calls one Jobs service and maps its result to a
status: a service ValueError is a 400, a None is a 404. Literal paths
(`/jobs/shifts`, `/paycheques/preview`) are declared above the `{id}` routes
that would otherwise parse them as ids.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app._database.dependencies import DBSession
from app.Auth.services.access import VerifiedUserId
from app.Jobs.schemas.job import (
    CashTipAccountChoice,
    CashTipAccountResult,
    Job,
    ShiftCreate,
    JobCreate,
    JobUpdate,
    ShiftOccurrence,
    ShiftRecord,
    ShiftRecordUpsert,
    ShiftScheduleCreate,
)
from app.Jobs.schemas.earnings import EarningsSummary
from app.Jobs.schemas.paycheque import PayCheck
from app.Jobs.services.paycheck_service import check_paycheque
from app.Jobs.services.earnings_service import earnings_summary
from app.Jobs.schemas.conflict import ShiftConflicts
from app.Jobs.schemas.tax_packet import TaxPacket
from app.Jobs.services.conflict_service import shift_conflicts
from app.Jobs.services.tax_packet_service import tax_packet
from app.Jobs.schemas.paycheque import (
    Paycheque,
    PaychequeCreate,
    PaychequePreview,
    PaychequeUpdate,
)
from app.Jobs.services.paycheque_service import (
    delete_paycheque,
    get_paycheque,
    list_paycheques,
    preview_paycheque,
    record_paycheque,
    update_paycheque,
)
from app.Jobs.services.job_service import (
    set_cash_tip_account,
    add_shift,
    confirm_shift,
    create_job,
    delete_job,
    get_job,
    list_jobs,
    list_shifts,
    remove_shift,
    set_shift_schedule,
    update_job,
)
from app.shared import audit
from app.shared.errors import error_user, responses
from app.Usage.services.usage_service import CREATE, record as record_usage

router = APIRouter()

JOB_404 = {404: {"description": "Job not found"}}
JOB_BOTH = {**JOB_404, 400: {"description": "Invalid job data"}}


# Phase 2 item 14 (D21): shifts against exams, and the year's tax packet.
@router.get("/{user_id}/shift-conflicts", response_model=ShiftConflicts, responses=responses["user_404"])
def get_shift_conflicts(user_id: VerifiedUserId, db: DBSession,
                        start: date | None = Query(default=None), end: date | None = Query(default=None)):
    """List shifts that overlap, or end too close before, the caller's exams.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        start: First exam date to report; defaults to today.
        end: Last exam date to report; defaults to 60 days after `start`.

    Returns:
        The exam buffer used and the conflicts.

    Raises:
        HTTPException: 400 if both dates are given and the window is inverted or
            longer than a year; 404 if the user does not exist.
    """
    if start and end and end < start:
        raise HTTPException(status_code=400, detail="The window ends before it starts")
    if start and end and (end - start).days > 366:
        raise HTTPException(status_code=400, detail="A window cannot be longer than a year")
    found = shift_conflicts(db, user_id, start, end)
    if found is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return found


@router.get("/{user_id}/tax-packet", response_model=TaxPacket, responses=responses["user_404"])
def get_tax_packet(user_id: VerifiedUserId, db: DBSession,
                   calendar_year: int = Query(..., ge=2000, le=2100)):
    """Get a calendar year's recorded pay, deductions, tips and tuition paid.

    `calendar_year` rather than `year`, because elsewhere in the API a year is a
    school year (1-10).

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        calendar_year: The calendar year, 2000-2100.

    Returns:
        The tax packet.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    found = tax_packet(db, user_id, calendar_year)
    if found is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])
    return found


@router.get("/{user_id}/jobs", response_model=list[Job], responses=responses["user_404"])
def get_jobs(
    user_id: VerifiedUserId,
    db: DBSession,
    include_archived: bool = Query(
        default=False, description="Also return jobs that have been archived"
    ),
):
    """List the caller's jobs, current ones first.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        include_archived: Also return archived jobs.

    Returns:
        The jobs, each with its next pay date.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    jobs = list_jobs(db, user_id, include_archived)
    if jobs is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return jobs


# Not under /jobs/: a sibling of /earnings and /paycheques, so no /jobs/{job_id}
# route can ever parse "cash-tip-account" as a job id, whatever the order here.
@router.put(
    "/{user_id}/cash-tip-account",
    response_model=CashTipAccountResult,
    responses=responses["user_both"],
)
def choose_cash_tip_account(user_id: VerifiedUserId, choice: CashTipAccountChoice, db: DBSession):
    """Choose the account cash tips go to, and file every tip held for want of one.

    Args:
        user_id: The verified caller's id.
        choice: The account, or null to clear the choice.
        db: Request-scoped database session.

    Returns:
        The account now chosen and how many held tips were filed.

    Raises:
        HTTPException: 404 if the account is not one of the caller's active
            accounts; nothing is written.
    """
    filed = set_cash_tip_account(db, user_id, choice.account_id)
    if filed is None:
        raise HTTPException(status_code=404, detail="That account is not one of yours, or is archived")
    return CashTipAccountResult(account_id=choice.account_id, filed=filed)


@router.post("/{user_id}/jobs", response_model=Job, responses=responses["user_both"])
def add_job(user_id: VerifiedUserId, job: JobCreate, db: DBSession):
    """Create a job.

    Args:
        user_id: The verified caller's id.
        job: The job and its pay schedule.
        db: Request-scoped database session.

    Returns:
        The created job.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    created = create_job(db, user_id, job)
    if created is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    record_usage(db, user_id, CREATE, "jobs")
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
    """List every shift date in a window, with what is known about each.

    A past shift nobody confirmed is returned at its scheduled hours with `assumed`
    set, never left out.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        start: First date of the window, inclusive.
        end: Last date of the window, inclusive.

    Returns:
        The shift occurrences, by date and start time.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    shifts = list_shifts(db, user_id, start, end)
    if shifts is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return shifts


@router.post(
    "/{user_id}/jobs/{job_id}/shifts",
    response_model=UUID,
    responses=JOB_BOTH,
)
def add_single_shift(
    user_id: VerifiedUserId, job_id: UUID, shift: ShiftCreate, db: DBSession
):
    """Add one shift on one date for one of the caller's jobs.

    Args:
        user_id: The verified caller's id.
        job_id: The job.
        shift: The date, times and location.
        db: Request-scoped database session.

    Returns:
        The new shift event's id.

    Raises:
        HTTPException: 404 if the job is missing or not the caller's.
    """
    created = add_shift(db, user_id, job_id, shift)
    if created is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return created


@router.delete(
    "/{user_id}/jobs/shifts/{event_id}",
    response_model=UUID,
    responses=JOB_BOTH,
)
def delete_single_shift(user_id: VerifiedUserId, event_id: UUID, db: DBSession):
    """Delete a one-off shift and everything recorded about it, cash tips included.

    Args:
        user_id: The verified caller's id.
        event_id: The shift event.
        db: Request-scoped database session.

    Returns:
        The deleted event's id.

    Raises:
        HTTPException: 400 if the shift comes from a weekly pattern (skip its date
            on the calendar instead); 404 if the shift is missing or not the
            caller's.
    """
    try:
        removed = remove_shift(db, user_id, event_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if removed is None:
        raise HTTPException(status_code=404, detail="Shift not found")

    return removed


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
    """Record what was actually worked on one date of a shift, replacing any record.

    Args:
        user_id: The verified caller's id.
        event_id: The shift event.
        on_date: The date of the occurrence.
        record: Worked times, confirmation, tip, rate override and notes.
        db: Request-scoped database session.

    Returns:
        The saved record.

    Raises:
        HTTPException: 404 if the event is not one of the caller's shifts.
    """
    try:
        saved = confirm_shift(db, user_id, event_id, on_date, record)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if saved is None:
        raise HTTPException(status_code=404, detail="Shift not found")

    return saved


@router.get(
    "/{user_id}/earnings",
    response_model=EarningsSummary,
    responses=responses["user_404"],
)
def get_earnings(user_id: VerifiedUserId, db: DBSession):
    """Get the caller's hours and money over the past week, the month and the term.

    Earned (predicted from shifts) and paid (cheques that arrived) are reported
    apart throughout.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.

    Returns:
        The earnings summary.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    summary = earnings_summary(db, user_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return summary


# Every literal path stays above /jobs/{job_id}, or it is parsed as a job id.
@router.get(
    "/{user_id}/paycheques",
    response_model=list[Paycheque],
    responses=responses["user_404"],
)
def get_paycheques(
    user_id: VerifiedUserId,
    db: DBSession,
    job_id: UUID | None = Query(default=None, description="Only this job's cheques"),
):
    """List the caller's paycheques, latest first.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        job_id: Only this job's cheques; omit for all.

    Returns:
        The cheques, with their deductions and variance.

    Raises:
        HTTPException: 404 if the user does not exist.
    """
    cheques = list_paycheques(db, user_id, job_id)
    if cheques is None:
        raise HTTPException(status_code=404, detail=error_user["not_found"])

    return cheques


@router.post(
    "/{user_id}/paycheques",
    response_model=Paycheque,
    responses=responses["user_both"],
)
def add_paycheque(user_id: VerifiedUserId, paycheque: PaychequeCreate, db: DBSession):
    """Record a cheque that arrived; only its net reaches the ledger.

    Args:
        user_id: The verified caller's id.
        paycheque: The cheque, its deductions and any allocations.
        db: Request-scoped database session.

    Returns:
        The recorded cheque.

    Raises:
        HTTPException: 400 if the net cannot be split (no income shares and no
            allocations) or an allocation names an account that is not the
            caller's; 404 if the job is missing or not the caller's.
    """
    try:
        created = record_paycheque(db, user_id, paycheque)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return created


@router.get(
    "/{user_id}/paycheques/preview",
    response_model=PaychequePreview,
    responses=JOB_404,
)
def preview(
    user_id: VerifiedUserId,
    db: DBSession,
    job_id: UUID = Query(..., description="The job being paid"),
    period_start: date = Query(..., description="First date of the pay period"),
    period_end: date = Query(..., description="Last date of the pay period"),
):
    """Get what the shifts in a pay period say a cheque for it should come to.

    Args:
        user_id: The verified caller's id.
        db: Request-scoped database session.
        job_id: The job being paid.
        period_start: First date of the pay period.
        period_end: Last date of the pay period.

    Returns:
        The expected gross and the shifts behind it.

    Raises:
        HTTPException: 400 if the period ends before it starts; 404 if the job is
            missing or not the caller's.
    """
    if period_end < period_start:
        raise HTTPException(status_code=400, detail="A pay period cannot end before it starts")

    expected = preview_paycheque(db, user_id, job_id, period_start, period_end)
    if expected is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return expected


@router.get(
    "/{user_id}/paycheques/{paycheque_id}/check",
    response_model=PayCheck,
    responses=JOB_404,
)
def check_single_paycheque(user_id: VerifiedUserId, paycheque_id: UUID, db: DBSession):
    """Check one of the caller's cheques against its shifts under BC's pay rules.

    Args:
        user_id: The verified caller's id.
        paycheque_id: The cheque.
        db: Request-scoped database session.

    Returns:
        The verdict, every line of the arithmetic with its rule, and notes.

    Raises:
        HTTPException: 404 if the cheque is missing or not the caller's.
    """
    result = check_paycheque(db, user_id, paycheque_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Paycheque not found")
    return result


@router.get(
    "/{user_id}/paycheques/{paycheque_id}",
    response_model=Paycheque,
    responses=JOB_404,
)
def get_single_paycheque(user_id: VerifiedUserId, paycheque_id: UUID, db: DBSession):
    """Get one of the caller's paycheques.

    Args:
        user_id: The verified caller's id.
        paycheque_id: The cheque.
        db: Request-scoped database session.

    Returns:
        The cheque.

    Raises:
        HTTPException: 404 if the cheque is missing or not the caller's.
    """
    cheque = get_paycheque(db, user_id, paycheque_id)
    if cheque is None:
        raise HTTPException(status_code=404, detail="Paycheque not found")

    return cheque


@router.patch(
    "/{user_id}/paycheques/{paycheque_id}",
    response_model=Paycheque,
    responses=JOB_BOTH,
)
def edit_paycheque(
    user_id: VerifiedUserId,
    paycheque_id: UUID,
    paycheque: PaychequeUpdate,
    db: DBSession,
):
    """Correct one of the caller's cheques; its ledger rows are rewritten to match.

    Args:
        user_id: The verified caller's id.
        paycheque_id: The cheque.
        paycheque: The fields to change.
        db: Request-scoped database session.

    Returns:
        The corrected cheque.

    Raises:
        HTTPException: 400 if the period would be inverted, the deductions would
            reach the gross, or the net cannot be split; 404 if the cheque is
            missing or not the caller's.
    """
    try:
        updated = update_paycheque(db, user_id, paycheque_id, paycheque)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="Paycheque not found")

    return updated


@router.delete(
    "/{user_id}/paycheques/{paycheque_id}",
    response_model=Paycheque,
    responses=JOB_404,
)
def remove_paycheque(user_id: VerifiedUserId, paycheque_id: UUID, db: DBSession):
    """Delete one of the caller's cheques and the ledger rows it wrote.

    Args:
        user_id: The verified caller's id.
        paycheque_id: The cheque.
        db: Request-scoped database session.

    Returns:
        A copy of the deleted cheque.

    Raises:
        HTTPException: 404 if the cheque is missing or not the caller's.
    """
    deleted = delete_paycheque(db, user_id, paycheque_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Paycheque not found")

    audit.deletion(
        "paycheque", user_id=user_id, target_id=paycheque_id,
        detail=f"{deleted.job_name} {deleted.gross_amount}",
    )
    return deleted


@router.get("/{user_id}/jobs/{job_id}", response_model=Job, responses=JOB_404)
def get_single_job(user_id: VerifiedUserId, job_id: UUID, db: DBSession):
    """Get one of the caller's jobs.

    Args:
        user_id: The verified caller's id.
        job_id: The job.
        db: Request-scoped database session.

    Returns:
        The job.

    Raises:
        HTTPException: 404 if the job is missing or not the caller's.
    """
    job = get_job(db, user_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return job


@router.patch("/{user_id}/jobs/{job_id}", response_model=Job, responses=JOB_BOTH)
def edit_job(user_id: VerifiedUserId, job_id: UUID, job: JobUpdate, db: DBSession):
    """Change the fields sent on one of the caller's jobs.

    Args:
        user_id: The verified caller's id.
        job_id: The job.
        job: The fields to change.
        db: Request-scoped database session.

    Returns:
        The updated job.

    Raises:
        HTTPException: 400 if both kinds of pay schedule would be set, the job
            would end before it starts, or its kind's pay field is missing; 404 if
            the job is missing or not the caller's.
    """
    try:
        updated = update_job(db, user_id, job_id, job)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return updated


@router.delete("/{user_id}/jobs/{job_id}", response_model=Job, responses=JOB_404)
def remove_job(user_id: VerifiedUserId, job_id: UUID, db: DBSession):
    """Delete a job entered by mistake, with its shifts, records and paycheques.

    Ending a job (`ended_on`) or archiving it keeps the history; this does not.
    Ledger rows already written stay.

    Args:
        user_id: The verified caller's id.
        job_id: The job.
        db: Request-scoped database session.

    Returns:
        A copy of the deleted job.

    Raises:
        HTTPException: 404 if the job is missing or not the caller's.
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
    """Replace one of the caller's jobs' weekly shift pattern; one-off shifts stay.

    Args:
        user_id: The verified caller's id.
        job_id: The job.
        schedule: The weekly blocks and, optionally, the dates.
        db: Request-scoped database session.

    Returns:
        The new shift events' ids.

    Raises:
        HTTPException: 400 if no start date is given or stored, or the dates are
            inverted; 404 if the job is missing or not the caller's.
    """
    try:
        created = set_shift_schedule(db, user_id, job_id, schedule)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return created
