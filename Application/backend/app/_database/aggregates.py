"""Reads of the sealed aggregates, each through its floor (Phase 3, D11).

Shared figures live in sealed tables that the API's role cannot read; on Postgres
every read here calls the one `SECURITY DEFINER` function that answers for its
table, and that function applies the floor itself. SQLite has no row security, so
there each read is a plain query applying the same rules; the tests run both.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app._database.models import COHORT_FLOOR, COUNTED_AFTER_DAYS, GradeDistributionModel

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
