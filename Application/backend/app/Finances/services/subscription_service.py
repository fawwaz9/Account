"""Service functions that find subscriptions nobody declared, and confirm them.

A candidate is a run of expenses with no `recurring_id`, on counted accounts,
sharing a normalised description, at least three long, with amounts within 10%
of their median and every gap inside one rhythm (weekly, fortnightly, monthly).
Nothing is stored: every call reads the ledger again.
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
from app.shared.money import money
from app.Finances.services.counted import on_counted_accounts

#: A trailing reference number -- "NETFLIX.COM 8842119", "Spotify #33012" -- is
#: how a payment processor tells two charges apart, not part of the merchant's
#: name. Stripped so the same subscription groups under one key instead of one
#: per invoice number.
_TRAILING_DIGITS = re.compile(r"\d{3,12}$")


def normalize(description: str | None) -> str:
    """Return a description normalised for grouping, its reference number removed.

    Lower-cased; a trailing run of 3-12 digits and trailing punctuation are removed.

    Args:
        description: A transaction description; may be None.

    Returns:
        The grouping key; "" for an empty description.
    """
    text = (description or "").strip().lower()
    text = _TRAILING_DIGITS.sub("", text)
    return text.rstrip(" #-_/").strip()


def capitalize(text: str) -> str:
    """Return text with only its first letter upper-cased, unlike `str.title`.

    Args:
        text: Text to adjust; may be empty.

    Returns:
        The text with its first character upper-cased.
    """
    return text[:1].upper() + text[1:] if text else text


def median(values: list[float]) -> float:
    """Return the median of a non-empty list of numbers.

    Args:
        values: At least one number.

    Returns:
        The middle value, or the mean of the two middle values.
    """
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def cadence_for_gaps(gaps: list[int]) -> str | None:
    """Return the rhythm every gap between charges fits, or None.

    One gap outside the rhythm disqualifies the whole run, since a false positive is
    worse than a miss.

    Args:
        gaps: Days between consecutive charges.

    Returns:
        "weekly", "fortnightly" or "monthly"; None when no rhythm fits every gap.
    """
    for cadence, (low, high) in CADENCE_GAP_DAYS.items():
        if all(low <= gap <= high for gap in gaps):
            return cadence
    return None


def next_expected(last_seen: date, cadence: str) -> date:
    """Return the date the next charge should land, one period after the last.

    A monthly date the next month lacks falls back to 30 days later.

    Args:
        last_seen: Date of the latest charge.
        cadence: "weekly", "fortnightly" or "monthly".

    Returns:
        The expected date of the next charge.
    """
    if cadence == "weekly":
        return last_seen + timedelta(days=7)
    if cadence == "fortnightly":
        return last_seen + timedelta(days=14)
    return add_months(last_seen, 1) or (last_seen + timedelta(days=30))


def recurrence_for(cadence: str) -> Recurrence:
    """Return the repeat rule a cadence becomes: weekly, every two weeks, or monthly.

    Args:
        cadence: "weekly", "fortnightly"; anything else is monthly.

    Returns:
        A rule with no weekdays and no end.
    """
    if cadence == "weekly":
        return Recurrence(freq=Frequency.WEEKLY, interval=1, byday=[], until=None, count=None)
    if cadence == "fortnightly":
        return Recurrence(freq=Frequency.WEEKLY, interval=2, byday=[], until=None, count=None)
    return Recurrence(freq=Frequency.MONTHLY, interval=1, byday=[], until=None, count=None)


def build_candidate(rows: list[TransactionModel], cadence: str) -> SubscriptionCandidate:
    """Build a finding from a qualifying run, with an instruction ready to submit.

    Args:
        rows: The run's expenses, oldest first.
        cadence: The rhythm they follow.

    Returns:
        The candidate; its suggestion takes the median amount and the latest
        charge's account and category, and starts one period after it.
    """
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
    """Return the user's undeclared repeating charges, most recently seen first.

    Args:
        db: Open database session.
        user_id: Whose ledger.

    Returns:
        The candidates; empty when none qualify; None when the user does not
        exist.
    """
    if not user_exists(db, user_id):
        return None

    rows = (
        db.query(TransactionModel)
        .filter(
            TransactionModel.user_id == user_id,
            TransactionModel.kind == EXPENSE,
            TransactionModel.recurring_id.is_(None),
            on_counted_accounts(user_id),  # D39
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
    """Create a standing instruction from a finding, and tag the charges behind it.

    Tagging the charges with the new rule's id is what stops the same run being
    found again. Two commits: the rule, then the tags.

    Args:
        db: Open database session.
        user_id: Whose ledger.
        transaction_ids: The finding's charges, as shown on the card.
        instruction: The standing instruction to create.

    Returns:
        The new instruction; None when the user does not exist.

    Raises:
        ValueError: If an account or the category is not the user's.
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
