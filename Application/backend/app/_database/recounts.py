"""The daily recount: every sealed aggregate rebuilt in one scheduler call (Phase 3, D11).

Each rebuild replaces its table whole and commits on its own, so one failing leaves
the others' fresh rows in place. The answer is how many rows each wrote, never
their contents.
"""
from collections.abc import Callable

from sqlalchemy.orm import Session

from app._database import aggregates, distributions

#: Answer key and rebuild, in order. "rows" is the grade counts', kept from Phase 2.
RECOUNTS: list[tuple[str, Callable[[Session], int]]] = [
    ("rows", distributions.recount),
    ("course_intel", aggregates.recount_course_intel),
]


def run_all(db: Session) -> dict[str, int]:
    """Rebuild every sealed aggregate.

    Args:
        db: Open session; needs no acting user.

    Returns:
        Each rebuild's answer key with how many rows it wrote.
    """
    return {key: rebuild(db) for key, rebuild in RECOUNTS}
