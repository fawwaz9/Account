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
    """``calendar_year``, not ``year``: everywhere else in the API a year is a
    school year (1-10), and the two must never be mistaken for each other."""
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
    """Every job, current ones first. A job you have left keeps its history."""
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
    """Choose the one account cash tips go to, and file every tip held for want of one.

    404 when the account is not one of yours, or is archived -- and then nothing
    is written, neither the choice nor any tip.
    """
    filed = set_cash_tip_account(db, user_id, choice.account_id)
    if filed is None:
        raise HTTPException(status_code=404, detail="That account is not one of yours, or is archived")
    return CashTipAccountResult(account_id=choice.account_id, filed=filed)


@router.post("/{user_id}/jobs", response_model=Job, responses=responses["user_both"])
def add_job(user_id: VerifiedUserId, job: JobCreate, db: DBSession):
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
    """Every shift date in the window, with what is known about each.

    A past shift nobody has confirmed is returned with its scheduled hours and
    `assumed` set, rather than left out: forgetting the admin should not make a
    fortnight of work read as an idle one.
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
    """Add one shift on one date.

    The ordinary way shifts arrive for part-time work, which is rarely the same
    hours every week. A repeating pattern is the exception and goes through
    /schedule instead.
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
    """Remove a one-off shift and anything recorded about it.

    A date generated by a pattern has no row to delete; cancelling one of those
    is a skipped date on the rule, which the calendar already offers.
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


@router.get(
    "/{user_id}/earnings",
    response_model=EarningsSummary,
    responses=responses["user_404"],
)
def get_earnings(user_id: VerifiedUserId, db: DBSession):
    """Hours and money over a week, a month and the term, from one pass.

    Earned and paid are reported separately throughout: earned comes from the
    shifts and is a prediction, paid comes from cheques that arrived. One
    combined figure would hide a fortnight of work nobody has paid for.
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
    """Record a cheque. Only the net reaches the ledger, split by income share."""
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
    """What the shifts in this period say the cheque should come to."""
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
    """This cheque against its shifts, BC overtime and vacation pay applied, with
    every line of the arithmetic and the rule each comes from."""
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
    """Correct a cheque. Its ledger rows are rewritten to match."""
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
    """Remove a cheque and the ledger rows it wrote."""
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
