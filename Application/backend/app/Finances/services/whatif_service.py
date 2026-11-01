"""The money what-if: the year plan re-run with changed inputs (Phase 4 item 14).

Starts from `plan_inputs`, the figures the year plan itself is worked out from,
and prices an hour through `main_hourly_job`, the solver's own rule, so a
scenario with nothing changed is the plan to the cent. Free, instant and exact:
the deterministic core paying rent (§13.5).

The line it doesn't cross: work hours move money here and nothing else. No
grade, study time or academic outcome is read or projected (§13.3, §13.5). The
calendar is read only for final exam dates, to suggest an "exam season" stretch;
the calendar may feed money, never the other way round.
"""

import uuid
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app._database.models import JobModel
from app.Calendar.schemas.event import EventKind
from app.Calendar.services.event_service import list_occurrences
from app.Finances.schemas.forecast import ForecastEvent
from app.Finances.schemas.whatif import ExamSeason, WhatIfIn, WhatIfOutcome, WhatIfPoint, WhatIfResult
from app.Finances.services.forecast_service import money_text, pay_dates, project
from app.Finances.services.plan_service import kept_share, main_hourly_job, plan_inputs
from app.Jobs.schemas.job import JobKind
from app.Jobs.services.earnings_service import earned_from_shifts
from app.Jobs.services.job_service import list_shifts
from app.shared.money import money

#: Days of no shifts the exam-season suggestion covers, ending on the last final.
EXAM_SEASON_DAYS = 21


def short(day: date) -> str:
    """Return a date as "Dec 3"."""
    return f"{day:%b} {day.day}"


def outcome(points, negative_on, lowest, lowest_on) -> WhatIfOutcome:
    """Return one side of the comparison, with the curve sampled weekly.

    Args:
        points: The daily balance points.
        negative_on: The first day below zero, if any.
        lowest: The lowest balance.
        lowest_on: Its day.

    Returns:
        The outcome; the curve keeps every seventh day and the last.
    """
    sampled = [p for i, p in enumerate(points) if i % 7 == 0 or i == len(points) - 1]
    return WhatIfOutcome(
        ending_balance=points[-1].balance, lowest_balance=lowest, lowest_on=lowest_on, negative_on=negative_on,
        points=[WhatIfPoint(on_date=p.on_date, balance=p.balance) for p in sampled],
    )


def exam_season(db: Session, user_id: uuid.UUID, start: date, end: date) -> ExamSeason | None:
    """Return the three weeks up to the last final exam in the window, if there is one.

    Args:
        db: Open database session.
        user_id: Whose calendar.
        start: The plan's first day.
        end: Its last day.

    Returns:
        The stretch, clipped to the plan; None with no final in the window.
    """
    finals = [o.on_date for o in (list_occurrences(db, user_id, start, end) or []) if o.kind == EventKind.FINAL.value]
    if not finals:
        return None
    last = max(finals)
    return ExamSeason(starts_on=max(start + timedelta(days=1), last - timedelta(days=EXAM_SEASON_DAYS - 1)), ends_on=last)


def what_if(db: Session, user_id: uuid.UUID, body: WhatIfIn, on_day: date | None = None) -> WhatIfResult | None:
    """Return the year plan as it stands beside the plan with a scenario's changes.

    Args:
        db: Open database session.
        user_id: Whose money.
        body: The changes.
        on_day: The day to plan from; defaults to the user's today.

    Returns:
        Baseline and scenario, the difference at the end, a suggested exam-season
        stretch, every assumption and every cap; None when the user does not exist.

    Raises:
        ValueError: If a date in the scenario falls outside the plan.
    """
    inputs = plan_inputs(db, user_id, on_day)
    if inputs is None:
        return None
    anchor, ends_on, share = inputs.anchor, inputs.ends_on, inputs.share

    for day in [body.hours_from, body.hours_until, body.no_shifts_from, body.no_shifts_until,
                *(p.on_date for p in body.purchases)]:
        if day is not None and not anchor < day <= ends_on:
            raise ValueError(f"Every date has to fall between tomorrow and {ends_on.isoformat()}, the plan's end")

    base = project(inputs.starting, inputs.daily, inputs.events, anchor, ends_on)
    assumptions = list(inputs.assumptions)
    capped: list[str] = []
    events: list[ForecastEvent] = [e.model_copy() for e in inputs.events]

    job, deduction = main_hourly_job(db, user_id, anchor)
    keep = kept_share(deduction)
    shifts = list_shifts(db, user_id, anchor + timedelta(days=1), ends_on, on_day=anchor) or []

    # A different wage scales the main job's upcoming cheques and prices any hours below.
    rate = job.hourly_rate if job else None
    if body.hourly_rate is not None:
        if job is None:
            capped.append("No hourly job with a rate, so a different wage changes nothing.")
        else:
            factor = body.hourly_rate / job.hourly_rate
            label = f"Pay: {job.name}"
            for event in events:
                if event.source == "pay" and event.description == label:
                    event.amount = money(event.amount * factor)
            rate = body.hourly_rate
            assumptions.append(
                f"{job.name} pays {money_text(body.hourly_rate)} an hour instead of {money_text(job.hourly_rate)}, "
                "on every upcoming cheque."
            )

    # A stretch with no shifts: each hourly shift in it comes off the cheque it would have been on.
    if body.no_shifts_from and body.no_shifts_until:
        jobs = {j.id: j for j in db.query(JobModel).filter(JobModel.user_id == user_id).all()}
        lost = 0.0
        for shift in shifts:
            if not body.no_shifts_from <= shift.on_date <= body.no_shifts_until:
                continue
            owner = jobs.get(shift.job_id)
            if owner is None or owner.kind != JobKind.HOURLY.value:
                continue
            gross, _ = earned_from_shifts(owner, [shift])
            if job is not None and owner.id == job.id and body.hourly_rate is not None and job.hourly_rate:
                gross *= body.hourly_rate / job.hourly_rate
            payday = next(iter(pay_dates(owner, shift.on_date, ends_on)), None)
            if payday is None or gross <= 0:
                continue
            amount = money(gross * keep * share)
            lost += amount
            events.append(ForecastEvent(on_date=payday, description=f"No shift: {owner.name}", amount=-amount,
                                        source="pay", split=True))
        assumptions.append(
            f"No shifts from {short(body.no_shifts_from)} to {short(body.no_shifts_until)}: "
            f"about {money_text(lost)} of pay doesn't come, each shift off the cheque it would have been on."
        )

    # More or fewer hours a week at the main job, landing at each week's end.
    if body.hours_per_week:
        if job is None or not rate:
            capped.append("No hourly job with a rate, so changed hours can't be priced.")
        else:
            start = max(body.hours_from or anchor + timedelta(days=1), anchor + timedelta(days=1))
            end = min(body.hours_until or ends_on, ends_on)
            scheduled: dict[date, float] = defaultdict(float)
            for shift in shifts:
                if shift.job_id == job.id:
                    scheduled[shift.on_date - timedelta(days=shift.on_date.weekday())] += shift.counted_minutes / 60
            net_hour = rate * keep * share
            trimmed = False
            day = start
            while day <= end:
                week_end = min(day + timedelta(days=6 - day.weekday()), end)
                fraction = ((week_end - day).days + 1) / 7
                hours = body.hours_per_week * fraction
                if hours < 0:
                    # Hours can only come off shifts that are on the schedule.
                    monday = day - timedelta(days=day.weekday())
                    available = scheduled.get(monday, 0.0)
                    if -hours > available:
                        hours = -available
                        trimmed = True
                if hours:
                    events.append(ForecastEvent(on_date=week_end, description=f"Changed hours: {job.name}",
                                                amount=money(hours * net_hour), source="pay", split=True))
                day = week_end + timedelta(days=1)
            if trimmed:
                capped.append("Some weeks have fewer scheduled hours than you took off; only those came off.")
            sign = "more" if body.hours_per_week > 0 else "fewer"
            assumptions.append(
                f"{abs(body.hours_per_week):g} {sign} hours a week at {job.name} from {short(start)} to {short(end)}, "
                f"at {money_text(rate)} an hour"
                + (f" after {deduction:g}% deductions" if deduction is not None else "")
                + ", counted at the end of each week rather than on paydays."
            )

    daily = inputs.daily
    if body.monthly_spending_change:
        wanted = inputs.daily + body.monthly_spending_change * 12 / 365
        if wanted < 0:
            capped.append("Day-to-day spending can't go below nothing, so it was set to $0 a day.")
            wanted = 0.0
        daily = wanted
        word = "more" if body.monthly_spending_change > 0 else "less"
        assumptions.append(f"Day-to-day spending {money_text(abs(body.monthly_spending_change))} a month {word}.")

    for purchase in body.purchases:
        events.append(ForecastEvent(on_date=purchase.on_date, description=purchase.label,
                                    amount=-money(purchase.amount), source="recurring", split=False))
    if body.purchases:
        assumptions.append("One-off purchases come out on the day you gave, from the liquid accounts.")

    scenario = project(inputs.starting, daily, events, anchor, ends_on)
    baseline_out = outcome(*base)
    scenario_out = outcome(*scenario)
    return WhatIfResult(
        starts_on=anchor,
        ends_on=ends_on,
        baseline=baseline_out,
        scenario=scenario_out,
        difference=money(scenario_out.ending_balance - baseline_out.ending_balance),
        exam_season=exam_season(db, user_id, anchor, ends_on),
        assumptions=assumptions,
        capped=capped,
    )
