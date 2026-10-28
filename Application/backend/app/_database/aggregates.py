"""Reads of the sealed aggregates, each through its floor (Phase 3, D11).

Shared figures live in sealed tables that the API's role cannot read; on Postgres
every read here calls the one `SECURITY DEFINER` function that answers for its
table, and that function applies the floor itself. SQLite has no row security, so
there each read is a plain query applying the same rules; the tests run both.
"""
import statistics
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app._database.models import (
    COHORT_FLOOR, COUNTED_AFTER_DAYS, OFFICE_HOUR_WINDOW_DAYS, CourseIntelModel, GradeDistributionModel,
    OfficeHourCheckinModel, OfficeHourSlotModel, TermReviewModel, UserModel, utc_now,
)

#: Month and day each term code's term ends, and the years to add to the code's
#: year: "2025W2" (Winter) ends on Apr 30, 2026.
TERM_ENDS = {"W1": (12, 31, 0), "W2": (4, 30, 1), "S1": (6, 30, 0), "S2": (8, 31, 0)}


def _is_postgres(db: Session) -> bool:
    """Return True when the session is bound to a Postgres database."""
    return db.get_bind().dialect.name == "postgresql"


def term_code_end(code: str | None) -> date | None:
    """Return the last day of the term a code such as "2025W1" names.

    Args:
        code: A term code: four digits of year, then W1, W2, S1 or S2.

    Returns:
        The term's last day; None for a code of any other shape.
    """
    if not code or len(code) != 6 or not code[:4].isdigit() or code[4:] not in TERM_ENDS:
        return None
    month, day, years = TERM_ENDS[code[4:]]
    return date(int(code[:4]) + years, month, day)


def term_closed(code: str | None, today: date) -> bool:
    """Return whether a term's answers may reach a shown figure today.

    Args:
        code: The term code.
        today: The day to judge by (UTC on Postgres, so the same here).

    Returns:
        True once `COUNTED_AFTER_DAYS` have passed since the term ended; False for an
        unreadable code.
    """
    ends = term_code_end(code)
    return ends is not None and ends + timedelta(days=COUNTED_AFTER_DAYS) < today


@dataclass(frozen=True)
class Band:
    """One band of one term's grade counts, as the read function answers it.

    Attributes:
        term_code: The term, such as "2025W1".
        bucket: The band's lower bound: 0 for below 50, then 50, 55 ... 95.
        contributors: Grades counted in the band.
    """
    term_code: str
    bucket: int
    contributors: int


def grade_distribution(db: Session, course_key: str, today: date) -> list[Band]:
    """Return a course's grade bands for every closed term at or above the floor.

    Args:
        db: Open session; on Postgres it must act as a signed-in user.
        course_key: The course, such as "UBCV CPSC 221".
        today: Today in UTC, used on SQLite only; Postgres reads its own clock.

    Returns:
        Bands, newest term first, lowest band first within a term; empty when no term
        qualifies.
    """
    if _is_postgres(db):
        rows = db.execute(text("SELECT * FROM account_grade_distribution(:k)"), {"k": course_key}).all()
        return [Band(r.term_code, r.bucket, r.contributors) for r in rows]
    by_term: dict[str, list[GradeDistributionModel]] = defaultdict(list)
    for row in db.query(GradeDistributionModel).filter(GradeDistributionModel.course_key == course_key):
        by_term[row.term_code].append(row)
    out = []
    for term in sorted(by_term, reverse=True):
        rows = by_term[term]
        if sum(r.contributors for r in rows) < COHORT_FLOOR or not term_closed(term, today):
            continue
        out += [Band(term, r.bucket, r.contributors) for r in sorted(rows, key=lambda r: r.bucket)]
    return out


def _utc_today() -> date:
    """Return today's date in UTC, the clock the Postgres functions read."""
    return datetime.now(timezone.utc).date()


@dataclass(frozen=True)
class CourseIntel:
    """What term reviews say about a course; each figure None below the floor.

    Attributes:
        hours_answers: People who gave weekly hours.
        hours_median: Their median weekly hours.
        difficulty_answers: People who rated difficulty.
        difficulty_mean: Mean difficulty, 1-5.
        clarity_answers: People who rated instructor clarity.
        clarity_mean: Mean clarity, 1-5.
        again_answers: People who said whether they'd take it again.
        again_share: Percentage of them who said yes.
    """
    hours_answers: int | None
    hours_median: float | None
    difficulty_answers: int | None
    difficulty_mean: float | None
    clarity_answers: int | None
    clarity_mean: float | None
    again_answers: int | None
    again_share: float | None


def _at_floor(answers: int | None, value):
    """Return `value` when `answers` reaches the floor, else None."""
    return value if answers is not None and answers >= COHORT_FLOOR else None


def recount_course_intel(db: Session, today: date | None = None) -> int:
    """Rebuild the course figures from scratch from every counted term review.

    One answer per person per course (their latest counted term's), from live
    accounts and reviews not skipped; a figure below the floor is written as null, and
    a course with none at the floor gets no row.

    Args:
        db: Open session; needs no acting user.
        today: Day to judge counted terms by, on SQLite only; None means today in UTC.

    Returns:
        The number of course rows written.

    Note:
        Deletes every existing row before writing, and commits.
    """
    if _is_postgres(db):
        written = db.execute(text("SELECT account_recount_course_intel()")).scalar()
        db.commit()
        return int(written or 0)
    today = today or _utc_today()
    db.query(CourseIntelModel).delete(synchronize_session=False)
    latest: dict[tuple[uuid.UUID, str], TermReviewModel] = {}
    rows = (
        db.query(TermReviewModel)
        .join(UserModel, UserModel.id == TermReviewModel.user_id)
        .filter(TermReviewModel.skipped.is_(False), UserModel.deleted_at.is_(None),
                TermReviewModel.course_key.isnot(None))
        .all()
    )
    for review in rows:
        if not term_closed(review.term_code, today):
            continue
        key = (review.user_id, review.course_key)
        if key not in latest or review.term_code > latest[key].term_code:
            latest[key] = review
    by_course: dict[str, list[TermReviewModel]] = defaultdict(list)
    for (_, course_key), review in latest.items():
        by_course[course_key].append(review)
    written = 0
    now = utc_now()
    for course_key, reviews in by_course.items():
        hours = [r.hours_per_week for r in reviews if r.hours_per_week is not None]
        difficulty = [r.difficulty for r in reviews if r.difficulty is not None]
        clarity = [r.clarity for r in reviews if r.clarity is not None]
        again = [r.would_take_again for r in reviews if r.would_take_again is not None]
        if max(len(hours), len(difficulty), len(clarity), len(again)) < COHORT_FLOOR:
            continue
        db.add(CourseIntelModel(
            course_key=course_key,
            hours_answers=_at_floor(len(hours), len(hours)),
            hours_median=_at_floor(len(hours), float(statistics.median(hours)) if hours else None),
            difficulty_answers=_at_floor(len(difficulty), len(difficulty)),
            difficulty_mean=_at_floor(len(difficulty), statistics.fmean(difficulty) if difficulty else None),
            clarity_answers=_at_floor(len(clarity), len(clarity)),
            clarity_mean=_at_floor(len(clarity), statistics.fmean(clarity) if clarity else None),
            again_answers=_at_floor(len(again), len(again)),
            again_share=_at_floor(len(again), 100.0 * sum(again) / len(again) if again else None),
            computed_at=now,
        ))
        written += 1
    db.commit()
    return written


def course_intel(db: Session, course_key: str) -> CourseIntel | None:
    """Return what term reviews say about a course, each figure through the floor.

    Args:
        db: Open session; on Postgres it must act as a signed-in user.
        course_key: The course, such as "UBCV CPSC 221".

    Returns:
        The figures, or None when the course has no row.
    """
    if _is_postgres(db):
        row = db.execute(text("SELECT * FROM account_course_intel(:k)"), {"k": course_key}).first()
        return None if row is None else CourseIntel(*row)
    row = db.query(CourseIntelModel).filter(CourseIntelModel.course_key == course_key).first()
    if row is None:
        return None
    return CourseIntel(
        _at_floor(row.hours_answers, row.hours_answers), _at_floor(row.hours_answers, row.hours_median),
        _at_floor(row.difficulty_answers, row.difficulty_answers),
        _at_floor(row.difficulty_answers, row.difficulty_mean),
        _at_floor(row.clarity_answers, row.clarity_answers), _at_floor(row.clarity_answers, row.clarity_mean),
        _at_floor(row.again_answers, row.again_answers), _at_floor(row.again_answers, row.again_share),
    )


@dataclass(frozen=True)
class Slot:
    """How busy one weekday-and-hour of a course's office hours usually is.

    Attributes:
        weekday: Local weekday, 0 Monday to 6 Sunday.
        hour: Local hour, 0-23.
        people: Distinct people whose check-in counted.
        none_votes: How many found no line.
        short_votes: How many found a short line.
        long_votes: How many found a long line.
    """
    weekday: int
    hour: int
    people: int
    none_votes: int
    short_votes: int
    long_votes: int


def recount_office_hours(db: Session, now: datetime | None = None) -> int:
    """Rebuild the office-hour slots from scratch from recent check-ins.

    Each person's latest check-in per course, weekday and hour in the last
    `OFFICE_HOUR_WINDOW_DAYS` counts once; live accounts only; no slot below the floor.

    Args:
        db: Open session; needs no acting user.
        now: The moment to measure the window from, on SQLite only (naive UTC).

    Returns:
        The number of slot rows written.

    Note:
        Deletes every existing row before writing, and commits.
    """
    if _is_postgres(db):
        written = db.execute(text("SELECT account_recount_office_hours()")).scalar()
        db.commit()
        return int(written or 0)
    since = (now or utc_now()) - timedelta(days=OFFICE_HOUR_WINDOW_DAYS)
    db.query(OfficeHourSlotModel).delete(synchronize_session=False)
    latest: dict[tuple, OfficeHourCheckinModel] = {}
    rows = (
        db.query(OfficeHourCheckinModel)
        .join(UserModel, UserModel.id == OfficeHourCheckinModel.user_id)
        .filter(UserModel.deleted_at.is_(None), OfficeHourCheckinModel.checked_at > since)
        .all()
    )
    for row in rows:
        key = (row.user_id, row.course_key, row.weekday, row.hour)
        if key not in latest or row.checked_at > latest[key].checked_at:
            latest[key] = row
    slots: dict[tuple, list[str]] = defaultdict(list)
    for (_, course_key, weekday, hour), row in latest.items():
        slots[(course_key, weekday, hour)].append(row.wait)
    written = 0
    stamp = utc_now()
    for (course_key, weekday, hour), waits in slots.items():
        if len(waits) < COHORT_FLOOR:
            continue
        db.add(OfficeHourSlotModel(course_key=course_key, weekday=weekday, hour=hour, people=len(waits),
                                   none_votes=waits.count("none"), short_votes=waits.count("short"),
                                   long_votes=waits.count("long"), computed_at=stamp))
        written += 1
    db.commit()
    return written


def office_hours(db: Session, course_key: str) -> list[Slot]:
    """Return a course's office-hour slots at the floor, by weekday then hour.

    Args:
        db: Open session; on Postgres it must act as a signed-in user.
        course_key: The course, such as "UBCV CPSC 221".

    Returns:
        The slots; empty when none has reached the floor.
    """
    if _is_postgres(db):
        rows = db.execute(text("SELECT * FROM account_office_hours(:k)"), {"k": course_key}).all()
        return [Slot(*row) for row in rows]
    rows = (
        db.query(OfficeHourSlotModel)
        .filter(OfficeHourSlotModel.course_key == course_key, OfficeHourSlotModel.people >= COHORT_FLOOR)
        .order_by(OfficeHourSlotModel.weekday, OfficeHourSlotModel.hour)
        .all()
    )
    return [Slot(r.weekday, r.hour, r.people, r.none_votes, r.short_votes, r.long_votes) for r in rows]
