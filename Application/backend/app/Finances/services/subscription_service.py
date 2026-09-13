"""Finding subscriptions nobody told the app about.

A standing instruction is a subscription the student already declared. This
looks for the ones they did not: an expense with no `recurring_id` behind it,
repeating on a description, an amount and a rhythm that together say "this is
not a coincidence." Only possible because standing instructions exist to
compare against -- an expense already tied to one is already known, and is
never reported here.

Nothing is stored. Every call re-reads the ledger and re-derives the pattern,
so there is nothing to go stale when a transaction is corrected or a
description is fixed.
"""

import re
import uuid
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app._database.models import TransactionModel
from app.Calendar.schemas.event import Frequency, Recurrence
from app.Calendar.utils.recurrence import add_months
from app.Finances.schemas.recurring import EXPENSE, RecurringCreate
from app.Finances.schemas.subscription import (
    AMOUNT_TOLERANCE,
    CADENCE_GAP_DAYS,
    MIN_OCCURRENCES,
    SubscriptionCandidate,
    SubscriptionOccurrence,
)
from app.Finances.services.recurring_service import create_rule
from app.Tasks.services.task_service import user_exists

#: A trailing reference number -- "NETFLIX.COM 8842119", "Spotify #33012" -- is
#: how a payment processor tells two charges apart, not part of the merchant's
#: name. Stripped so the same subscription groups under one key instead of one
#: per invoice number.
_TRAILING_DIGITS = re.compile(r"\d{3,12}$")


def money(value: float) -> float:
    return round(value + 0.0, 2)


def normalize(description: str | None) -> str:
    text = (description or "").strip().lower()
    text = _TRAILING_DIGITS.sub("", text)
    return text.rstrip(" #-_/").strip()


def capitalize(text: str) -> str:
    """Just the first letter. `str.title()` would turn "netflix.com" into
    "Netflix.Com" -- every letter after a non-letter is not the start of a
    word here, only the description is."""
    return text[:1].upper() + text[1:] if text else text


def median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def cadence_for_gaps(gaps: list[int]) -> str | None:
    """Which rhythm every gap in the run agrees with, or none.

    One gap outside the window is enough to disqualify the run: a subscription
    that skipped a month is not distinguishable here from two unrelated charges
    that happened to repeat twice, and the false positive is worse than the
    miss.
    """
    for cadence, (low, high) in CADENCE_GAP_DAYS.items():
        if all(low <= gap <= high for gap in gaps):
            return cadence
    return None


def next_expected(last_seen: date, cadence: str) -> date:
    if cadence == "weekly":
        return last_seen + timedelta(days=7)
    if cadence == "fortnightly":
        return last_seen + timedelta(days=14)
    return add_months(last_seen, 1) or (last_seen + timedelta(days=30))


def recurrence_for(cadence: str) -> Recurrence:
    if cadence == "weekly":
        return Recurrence(freq=Frequency.WEEKLY, interval=1, byday=[], until=None, count=None)
    if cadence == "fortnightly":
        return Recurrence(freq=Frequency.WEEKLY, interval=2, byday=[], until=None, count=None)
    return Recurrence(freq=Frequency.MONTHLY, interval=1, byday=[], until=None, count=None)


def build_candidate(rows: list[TransactionModel], cadence: str) -> SubscriptionCandidate:
    amounts = [abs(row.amount) for row in rows]
    last = rows[-1]
    starts_on = next_expected(last.occurred_on, cadence)

    return SubscriptionCandidate(
        description=last.description or "",
        account_id=last.account_id,
        category_id=last.category_id,
        cadence=cadence,
        median_amount=money(median(amounts)),
        first_seen=rows[0].occurred_on,
        last_seen=last.occurred_on,
        next_expected_on=starts_on,
        occurrences=[
            SubscriptionOccurrence(transaction_id=row.id, on_date=row.occurred_on, amount=money(abs(row.amount)))
            for row in rows
        ],
        suggested=RecurringCreate(
            kind=EXPENSE,
            amount=money(median(amounts)),
            description=capitalize(normalize(last.description)) or (last.description or ""),
            account_id=last.account_id,
            category_id=last.category_id,
            starts_on=starts_on,
            recurrence=recurrence_for(cadence),
            active=True,
        ),
    )


def find_subscriptions(db: Session, user_id: uuid.UUID) -> list[SubscriptionCandidate] | None:
    if not user_exists(db, user_id):
        return None

    rows = (
        db.query(TransactionModel)
        .filter(
            TransactionModel.user_id == user_id,
            TransactionModel.kind == EXPENSE,
            TransactionModel.recurring_id.is_(None),
        )
        .order_by(TransactionModel.occurred_on)
        .all()
    )

    groups: dict[str, list[TransactionModel]] = defaultdict(list)
    for row in rows:
        key = normalize(row.description)
        if key:
            groups[key].append(row)

    candidates = []
    for group in groups.values():
        if len(group) < MIN_OCCURRENCES:
            continue

        amounts = [abs(row.amount) for row in group]
        med = median(amounts)
        if med <= 0 or any(abs(amount - med) > med * AMOUNT_TOLERANCE for amount in amounts):
            continue

        gaps = [(later.occurred_on - earlier.occurred_on).days for earlier, later in zip(group, group[1:])]
        cadence = cadence_for_gaps(gaps)
        if cadence is None:
            continue

        candidates.append(build_candidate(group, cadence))

    candidates.sort(key=lambda candidate: candidate.last_seen, reverse=True)
    return candidates


def confirm_subscription(
    db: Session, user_id: uuid.UUID, transaction_ids: list[uuid.UUID], instruction: RecurringCreate
):
    """Create the standing instruction, and tag the history that justified it.

    Without the second half, the charges that made the case would still show
    no `recurring_id` and the exact same run would qualify as a pattern again
    on the next read -- a confirmed subscription that never stops being found.
    """
    rule = create_rule(db, user_id, instruction)
    if rule is None:
        return None

    if transaction_ids:
        db.query(TransactionModel).filter(
            TransactionModel.user_id == user_id,
            TransactionModel.id.in_(transaction_ids),
        ).update({"recurring_id": rule.id}, synchronize_session=False)
        db.commit()

    return rule
