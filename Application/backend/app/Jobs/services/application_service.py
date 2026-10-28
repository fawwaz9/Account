"""Service functions for the job application tracker and its recruiting seasons.

Every function reads and writes only the caller's own rows. An application's
`status` is just its latest step, kept so a list need not read each history;
replies, days to a reply and the Sankey are all read from `application_steps`.
"""
from __future__ import annotations

import statistics
import uuid
from datetime import date

from sqlalchemy.orm import Session, selectinload

from app._database.models import ApplicationSeasonModel, ApplicationStepModel, JobApplicationModel, utc_now
from app.Jobs.schemas.application import (
    Application, ApplicationIn, ApplicationStats, ApplicationUpdate, Flow, Season, SeasonIn, Step, StepIn,
)
from app.shared.dates import user_for, user_today

#: Quiet this long while still waiting on them, and "no reply yet?" is asked (D3).
QUIET_DAYS = 30

#: Still waiting on someone.
WAITING_ON_THEM = {"applied", "screening", "interview"}
#: Not finished: waiting on them, or an offer waiting on you.
OPEN = WAITING_ON_THEM | {"offer"}
#: Any answer at all from the employer.
REPLIES = {"screening", "interview", "offer", "accepted", "rejected"}


def _own(db: Session, user_id: uuid.UUID, application_id: uuid.UUID) -> JobApplicationModel | None:
    """Return the caller's application with its steps loaded, or None."""
    return (
        db.query(JobApplicationModel)
        .options(selectinload(JobApplicationModel.steps))
        .filter(JobApplicationModel.id == application_id, JobApplicationModel.user_id == user_id)
        .first()
    )


def _ordered(row: JobApplicationModel) -> list[ApplicationStepModel]:
    """Return an application's steps by date, then by when they were recorded."""
    return sorted(row.steps, key=lambda step: (step.on_date, step.created_at or utc_now()))


def _settle(row: JobApplicationModel) -> None:
    """Set an application's status to its latest step's, and stamp `updated_at`."""
    steps = _ordered(row)
    row.status = steps[-1].status if steps else "applied"
    row.updated_at = utc_now()


def as_schema(row: JobApplicationModel, today: date) -> Application:
    """Build an application's response, with its last step and whether it is quiet.

    Args:
        row: The application with its steps loaded.
        today: The user's today, for the 30-day quiet check.

    Returns:
        The application with its steps oldest first.
    """
    steps = _ordered(row)
    last = steps[-1].on_date if steps else row.applied_on
    return Application(
        id=row.id, company=row.company, role=row.role, applied_on=row.applied_on,
        source=row.source, link=row.link, location=row.location, notes=row.notes,
        status=row.status, deadline=row.deadline, follow_up_on=row.follow_up_on,
        offer_amount=row.offer_amount, offer_period=row.offer_period,
        steps=[Step(id=step.id, status=step.status, on_date=step.on_date, note=step.note) for step in steps],
        last_step_on=last,
        quiet=row.status in WAITING_ON_THEM and (today - last).days >= QUIET_DAYS,
        created_at=row.created_at, updated_at=row.updated_at,
    )


def _all(db: Session, user_id: uuid.UUID, season: ApplicationSeasonModel | None = None) -> list[JobApplicationModel]:
    """Return the caller's applications, newest applied first, optionally in a season.

    A season includes every application whose applied date falls in its months.
    """
    query = (
        db.query(JobApplicationModel)
        .options(selectinload(JobApplicationModel.steps))
        .filter(JobApplicationModel.user_id == user_id)
    )
    if season is not None:
        # The day applied, within the season's months, the end month whole (D7).
        first, after = season_window(season)
        query = query.filter(JobApplicationModel.applied_on >= first, JobApplicationModel.applied_on < after)
    return query.order_by(JobApplicationModel.applied_on.desc(), JobApplicationModel.created_at.desc()).all()


class NoSuchSeason(Exception):
    """Raised when a season id is not one of the caller's; answered as a 404."""


def _season_for(db: Session, user_id: uuid.UUID, season_id: uuid.UUID | None) -> ApplicationSeasonModel | None:
    """Return the caller's season for an id, or None when no id is given.

    Raises NoSuchSeason when the id is not one of the caller's seasons.
    """
    if season_id is None:
        return None
    season = _own_season(db, user_id, season_id)
    if season is None:
        raise NoSuchSeason
    return season


def list_applications(db: Session, user_id: uuid.UUID, season_id: uuid.UUID | None = None) -> list[Application] | None:
    """Return the caller's applications, newest applied first.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        season_id: Only applications applied for within this season's months;
            None for all.

    Returns:
        The applications; None when the user does not exist.

    Raises:
        NoSuchSeason: If `season_id` is not one of the caller's seasons.
    """
    if user_for(db, user_id) is None:
        return None
    today = user_today(db, user_id)
    return [as_schema(row, today) for row in _all(db, user_id, _season_for(db, user_id, season_id))]


def _clean(text: str | None) -> str | None:
    """Return text stripped, or None when it is empty or missing."""
    return (text or "").strip() or None


def create(db: Session, user_id: uuid.UUID, data: ApplicationIn) -> Application | None:
    """Record a new job application, with its first "applied" step.

    Commits.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        data: The application; company and role are stripped, empty optional text
            becomes None.

    Returns:
        The new application; None when the user does not exist.
    """
    if user_for(db, user_id) is None:
        return None
    now = utc_now()
    row = JobApplicationModel(
        id=uuid.uuid4(), user_id=user_id, company=data.company.strip(), role=data.role.strip(),
        applied_on=data.applied_on, source=_clean(data.source), link=_clean(data.link),
        location=_clean(data.location), notes=_clean(data.notes), status="applied",
        deadline=data.deadline, follow_up_on=data.follow_up_on,
        offer_amount=data.offer_amount, offer_period=data.offer_period.value if data.offer_period else None,
        created_at=now, updated_at=now,
    )
    # The first step is written with the application, so every history starts
    # where the application did.
    row.steps.append(ApplicationStepModel(id=uuid.uuid4(), status="applied", on_date=data.applied_on, created_at=now))
    db.add(row)
    db.commit()
    return as_schema(_own(db, user_id, row.id), user_today(db, user_id))


def update(db: Session, user_id: uuid.UUID, application_id: uuid.UUID, data: ApplicationUpdate) -> Application | None:
    """Change the fields sent on one of the caller's applications.

    A new `applied_on` moves the "applied" step with it. The offer's amount and
    period are checked as a pair against the stored row. Commits.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        application_id: The application.
        data: The fields to change.

    Returns:
        The updated application; None when it is not the caller's.

    Raises:
        ValueError: If company or role would be blank, only one half of the offer's
            pay would be set, or a later step is dated before the new
            `applied_on`.
    """
    row = _own(db, user_id, application_id)
    if row is None:
        return None
    fields = data.model_dump(exclude_unset=True)

    for key in ("company", "role"):
        if key in fields:
            if not (fields[key] or "").strip():
                raise ValueError("An application needs a company and a role")
            setattr(row, key, fields[key].strip())
    for key in ("source", "link", "location", "notes"):
        if key in fields:
            setattr(row, key, _clean(fields[key]))
    for key in ("deadline", "follow_up_on"):
        if key in fields:
            setattr(row, key, fields[key])
    if "offer_amount" in fields:
        row.offer_amount = fields["offer_amount"]
    if "offer_period" in fields:
        row.offer_period = fields["offer_period"].value if fields["offer_period"] else None
    if (row.offer_amount is None) != (row.offer_period is None):
        raise ValueError("An offer's pay needs both an amount and how often")

    if fields.get("applied_on") is not None:
        applied_on = fields["applied_on"]
        later = [step for step in row.steps if step.status != "applied"]
        if any(step.on_date < applied_on for step in later):
            raise ValueError("Something already happened before that date")
        row.applied_on = applied_on
        # The first step moves with the application's date.
        for step in row.steps:
            if step.status == "applied":
                step.on_date = applied_on

    _settle(row)
    db.commit()
    return as_schema(_own(db, user_id, application_id), user_today(db, user_id))


def delete(db: Session, user_id: uuid.UUID, application_id: uuid.UUID) -> bool | None:
    """Delete one of the caller's applications with its whole history.

    Commits.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        application_id: The application.

    Returns:
        True when deleted; None when it is not the caller's.
    """
    row = _own(db, user_id, application_id)
    if row is None:
        return None
    db.delete(row)
    db.commit()
    return True


def add_step(db: Session, user_id: uuid.UUID, application_id: uuid.UUID, data: StepIn) -> Application | None:
    """Record a status change on one of the caller's applications.

    The application's status becomes whichever step is now latest by date. Commits.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        application_id: The application.
        data: The status, its date and an optional note.

    Returns:
        The updated application; None when it is not the caller's.

    Raises:
        ValueError: If the step is dated before the application.
    """
    row = _own(db, user_id, application_id)
    if row is None:
        return None
    if data.on_date < row.applied_on:
        raise ValueError("That is before you applied")
    row.steps.append(ApplicationStepModel(
        id=uuid.uuid4(), status=data.status.value, on_date=data.on_date,
        note=_clean(data.note), created_at=utc_now(),
    ))
    _settle(row)
    db.commit()
    return as_schema(_own(db, user_id, application_id), user_today(db, user_id))


def delete_step(db: Session, user_id: uuid.UUID, application_id: uuid.UUID, step_id: uuid.UUID) -> Application | None:
    """Take back a step entered by mistake; the status falls back to the latest left.

    The first "applied" step goes only with the application. Commits.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        application_id: The application.
        step_id: The step.

    Returns:
        The updated application; None when the application or step is not the
        caller's.

    Raises:
        ValueError: If the step is the "applied" step.
    """
    row = _own(db, user_id, application_id)
    if row is None:
        return None
    step = next((item for item in row.steps if item.id == step_id), None)
    if step is None:
        return None
    if step.status == "applied":
        raise ValueError("Every application starts as applied; delete the application instead")
    row.steps.remove(step)
    _settle(row)
    db.commit()
    return as_schema(_own(db, user_id, application_id), user_today(db, user_id))


def path_of(row: JobApplicationModel) -> list[str]:
    """Return the stages one application passed through, for the Sankey.

    Repeated statuses (interview rounds) collapse into one stage, a "no reply"
    followed by a later step is dropped, and an application still open ends in
    "waiting".

    Args:
        row: The application with its steps loaded.

    Returns:
        The stage names in order, starting with "applied".
    """
    statuses = [step.status for step in _ordered(row)]
    statuses = [status for at, status in enumerate(statuses)
                if status != "no_reply" or at == len(statuses) - 1]
    path: list[str] = []
    for status in statuses:
        if not path or path[-1] != status:
            path.append(status)
    if path[-1] in OPEN:
        path.append("waiting")
    return path


def stats(db: Session, user_id: uuid.UUID, season_id: uuid.UUID | None = None) -> ApplicationStats | None:
    """Return the reply, interview and offer figures for the caller's applications.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        season_id: Only applications within this season's months; None for all.

    Returns:
        The figures and Sankey flows; None when the user does not exist.

    Raises:
        NoSuchSeason: If `season_id` is not one of the caller's seasons.
    """
    if user_for(db, user_id) is None:
        return None
    rows = _all(db, user_id, _season_for(db, user_id, season_id))

    days_to_reply: list[int] = []
    replied = interviews = offers = accepted = 0
    by_status: dict[str, int] = {}
    flows: dict[tuple[str, str], int] = {}

    for row in rows:
        by_status[row.status] = by_status.get(row.status, 0) + 1
        seen = {step.status for step in row.steps}
        first_reply = next((step for step in _ordered(row) if step.status in REPLIES), None)
        if first_reply is not None:
            replied += 1
            days_to_reply.append((first_reply.on_date - row.applied_on).days)
        interviews += "interview" in seen
        offers += "offer" in seen or "accepted" in seen
        accepted += "accepted" in seen

        path = path_of(row)
        for source, target in zip(path, path[1:]):
            flows[(source, target)] = flows.get((source, target), 0) + 1

    total = len(rows)
    return ApplicationStats(
        total=total,
        open=sum(1 for row in rows if row.status in OPEN),
        replied=replied,
        reply_rate=round(replied / total, 3) if total else None,
        median_days_to_reply=float(statistics.median(days_to_reply)) if days_to_reply else None,
        interviews=interviews,
        offers=offers,
        accepted=accepted,
        by_status=by_status,
        flows=[Flow(source=s, target=t, count=n) for (s, t), n in sorted(flows.items(), key=lambda item: -item[1])],
    )


# --- seasons (D7) -------------------------------------------------------------

def _month(text: str) -> date:
    """Return the first day of a month written YYYY-MM."""
    year, month = map(int, text.split("-"))
    return date(year, month, 1)


def season_window(season: ApplicationSeasonModel) -> tuple[date, date]:
    """Return a season's first day and the first day after its last month.

    Args:
        season: The season row.

    Returns:
        (first day, first day after the end month), a half-open range.
    """
    end = season.ends_month
    after = date(end.year + (end.month == 12), end.month % 12 + 1, 1)
    return season.starts_month, after


def season_schema(season: ApplicationSeasonModel) -> Season:
    """Build a season's response, with its months written YYYY-MM.

    Args:
        season: The stored season.

    Returns:
        The season with `starts` and `ends` as YYYY-MM strings.
    """
    return Season(id=season.id, name=season.name,
                  starts=season.starts_month.strftime("%Y-%m"), ends=season.ends_month.strftime("%Y-%m"))


def _own_season(db: Session, user_id: uuid.UUID, season_id: uuid.UUID) -> ApplicationSeasonModel | None:
    """Return the caller's season with this id, or None."""
    return (
        db.query(ApplicationSeasonModel)
        .filter(ApplicationSeasonModel.id == season_id, ApplicationSeasonModel.user_id == user_id)
        .first()
    )


def list_seasons(db: Session, user_id: uuid.UUID) -> list[Season] | None:
    """Return the caller's recruiting seasons, latest start first, then by name.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.

    Returns:
        The seasons; None when the user does not exist.
    """
    if user_for(db, user_id) is None:
        return None
    rows = (
        db.query(ApplicationSeasonModel)
        .filter(ApplicationSeasonModel.user_id == user_id)
        .order_by(ApplicationSeasonModel.starts_month.desc(), ApplicationSeasonModel.name)
        .all()
    )
    return [season_schema(row) for row in rows]


def create_season(db: Session, user_id: uuid.UUID, data: SeasonIn) -> Season | None:
    """Create a recruiting season for the caller.

    Commits.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        data: The name (stripped) and the first and last months.

    Returns:
        The new season; None when the user does not exist.
    """
    if user_for(db, user_id) is None:
        return None
    row = ApplicationSeasonModel(id=uuid.uuid4(), user_id=user_id, name=data.name.strip(),
                                 starts_month=_month(data.starts), ends_month=_month(data.ends), created_at=utc_now())
    db.add(row)
    db.commit()
    return season_schema(row)


def update_season(db: Session, user_id: uuid.UUID, season_id: uuid.UUID, data: SeasonIn) -> Season | None:
    """Replace one of the caller's seasons' name and months.

    Commits.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        season_id: The season.
        data: The new name and months.

    Returns:
        The updated season; None when it is not the caller's.
    """
    row = _own_season(db, user_id, season_id)
    if row is None:
        return None
    row.name, row.starts_month, row.ends_month = data.name.strip(), _month(data.starts), _month(data.ends)
    db.commit()
    return season_schema(row)


def delete_season(db: Session, user_id: uuid.UUID, season_id: uuid.UUID) -> bool | None:
    """Delete one of the caller's seasons; its applications are untouched.

    Commits.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        season_id: The season.

    Returns:
        True when deleted; None when it is not the caller's.
    """
    row = _own_season(db, user_id, season_id)
    if row is None:
        return None
    db.delete(row)
    db.commit()
    return True
