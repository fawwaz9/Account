"""The year plan against what happened, month by month (Phase 1 D37).

The plan is recomputed on every read, so on its own it can never be wrong --
which is why §13.4's third part needs a *saved* plan. The student saves one;
each save is kept. A finished month is compared with the newest plan saved
before that month began: a plan saved on March 14 has a March row covering only
the 15th onward, so setting it against all of March would blame the plan for
two weeks it never forecast.

Actuals are read from the ledger by the plan's own definitions, or the
comparison would measure the definitions rather than the month:

* **Liquid money** is spending, savings and emergency accounts, archived ones
  included -- an account closed in May still held March's money.
* **Transfers between liquid accounts** net to nothing. A transfer to or from
  anything else (investments, "other") is money out or in.
* **Card purchases count when they happen,** as the plan's pace does, and paying
  the card off counts for nothing: counting both would charge the month twice.
* **Tuition counts,** because it left. The plan leaves it out, so each month
  says how much of the gap it explains.
"""

import uuid
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import false, func
from sqlalchemy.orm import Session

from app._database.models import AccountModel, SavedPlanModel, TransactionModel
from app.Finances.schemas.plan import MonthReview, PlanReview, SavedPlan
from app.Finances.services.forecast_service import LIQUID_KINDS, tuition_transaction_ids
from app.Finances.services.plan_service import plan
from app.shared.dates import user_today
from app.shared.money import money


def save_plan(db: Session, user_id: uuid.UUID) -> SavedPlanModel | None:
    """Keep the plan as it stands today. Never replaces an earlier one."""
    today = user_today(db, user_id)
    current = plan(db, user_id, on_day=today)
    if current is None:
        return None
    row = SavedPlanModel(
        id=uuid.uuid4(),
        user_id=user_id,
        saved_on=today,
        starts_on=current.starts_on,
        ends_on=current.ends_on,
        starting_balance=current.starting_balance,
        months=[
            {
                "month": m.month.isoformat(),
                "money_in": m.money_in,
                "money_out": m.money_out,
                "end_balance": m.end_balance,
            }
            for m in current.months
        ],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def first_of_next(day: date) -> date:
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def review(db: Session, user_id: uuid.UUID, on_day: date | None = None) -> PlanReview:
    today = on_day or user_today(db, user_id)
    saved = (
        db.query(SavedPlanModel)
        .filter(SavedPlanModel.user_id == user_id)
        .order_by(SavedPlanModel.saved_at)
        .all()
    )
    if not saved:
        return PlanReview()

    # Each finished month, against the newest plan saved before it began.
    this_month = today.replace(day=1)
    planned: dict[date, tuple[SavedPlanModel, dict]] = {}
    for row in saved:  # oldest first, so a newer plan overwrites an older one
        for entry in row.months or []:
            month = date.fromisoformat(entry["month"])
            if row.saved_on < month < this_month:
                planned[month] = (row, entry)
    if not planned:
        return PlanReview(latest=SavedPlan.model_validate(saved[-1]))

    months = sorted(planned)
    actual = actuals(db, user_id, months[0], first_of_next(months[-1]) - timedelta(days=1))
    reviewed = []
    for month in months:
        row, entry = planned[month]
        got = actual[month]
        reviewed.append(MonthReview(
            month=month,
            plan_saved_on=row.saved_on,
            planned_in=entry["money_in"],
            planned_out=entry["money_out"],
            planned_end=entry["end_balance"],
            actual_in=money(got["in"]),
            actual_out=money(got["out"]),
            actual_end=money(got["end"]),
            tuition_out=money(got["tuition"]),
        ))
    return PlanReview(latest=SavedPlan.model_validate(saved[-1]), months=reviewed)


def actuals(db: Session, user_id: uuid.UUID, first: date, last: date) -> dict[date, dict[str, float]]:
    """Money in, out, tuition, and the closing liquid balance, per month from `first` to `last`."""
    # Accounts that count (D39). An unticked one is as if absent: its own rows
    # are skipped, and money moved to it counts as leaving.
    kinds = dict(
        db.query(AccountModel.id, AccountModel.kind)
        .filter(AccountModel.user_id == user_id, AccountModel.counts_toward_net_worth.is_(True))
        .all()
    )
    liquid = {account for account, kind in kinds.items() if kind in LIQUID_KINDS}
    debt = {account for account, kind in kinds.items() if kind == "debt"}
    tuition = tuition_transaction_ids(db, user_id)

    rows = (
        db.query(TransactionModel)
        .filter(
            TransactionModel.user_id == user_id,
            TransactionModel.occurred_on >= first,
            TransactionModel.occurred_on <= last,
        )
        .all()
    )
    # A transfer's other half, to tell a move between liquid accounts (nothing)
    # from one out to investments (money out). Read from the whole ledger, since
    # the halves of a transfer on the 31st can be dated a day apart.
    groups = {row.group_id for row in rows if row.kind == "transfer" and row.group_id}
    halves: dict[uuid.UUID, list[TransactionModel]] = defaultdict(list)
    if groups:
        for half in db.query(TransactionModel).filter(
            TransactionModel.user_id == user_id, TransactionModel.group_id.in_(groups)
        ):
            halves[half.group_id].append(half)

    totals: dict[date, dict[str, float]] = defaultdict(lambda: {"in": 0.0, "out": 0.0, "tuition": 0.0, "end": 0.0})
    for row in rows:
        month = totals[row.occurred_on.replace(day=1)]
        if row.account_id in debt:
            if row.kind == "expense":  # a card purchase; paying the card is a transfer
                month["out"] -= row.amount
            continue
        if row.account_id not in liquid:
            continue
        if row.kind == "income":
            month["in"] += row.amount
        elif row.kind == "expense":
            month["out"] -= row.amount  # a refund (positive) lowers it
            if row.id in tuition:
                month["tuition"] -= row.amount
        elif row.kind == "transfer":
            other = [h for h in halves.get(row.group_id, []) if h.id != row.id]
            if other and (other[0].account_id in liquid or other[0].account_id in debt):
                continue  # between liquid accounts, or paying a card
            if row.amount > 0:
                month["in"] += row.amount
            else:
                month["out"] -= row.amount

    # The closing balance: everything in a liquid account up to the month's end.
    month = first
    while month <= last:
        end = first_of_next(month) - timedelta(days=1)
        closing = (
            db.query(func.sum(TransactionModel.amount))
            .filter(
                TransactionModel.user_id == user_id,
                TransactionModel.account_id.in_(liquid) if liquid else false(),
                TransactionModel.occurred_on <= end,
            )
            .scalar()
        )
        totals[month]["end"] = closing or 0.0
        month = first_of_next(month)
    return totals
