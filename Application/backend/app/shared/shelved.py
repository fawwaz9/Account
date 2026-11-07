"""Shelved modules: kept in the code and the database, but closed to every request.

A shelved module's router is still mounted, behind `shelf(name)`, so each of its
routes answers 404 before authentication, path checks or the database are reached.
Nothing is deleted: the code, its tables and every row stay, and taking a name out
of `SHELVED` reopens the module on the next deploy.

The test suite empties `SHELVED` (conftest.py), so the shelved code keeps running
in every suite and doesn't rot; `test_shelved.py` checks the shelf itself.
"""
from typing import Callable

from fastapi import HTTPException

#: Modules closed to requests. Fitness, teams and clubs since 2026-11-07: the owner
#: judged the body room far from production-ready.
SHELVED: set[str] = {"fitness", "teams", "clubs"}

SHELVED_DETAIL = "This feature is shelved."
"""The 404's detail, the same for every route of every shelved module."""


def shelf(name: str) -> Callable[[], None]:
    """Return a router dependency that refuses every request while `name` is shelved.

    Args:
        name: The module's key in `SHELVED`.

    Returns:
        A dependency for `include_router(..., dependencies=[Depends(...)])`. It reads
        `SHELVED` on each request, so tests can open the shelf.
    """
    def closed() -> None:
        if name in SHELVED:
            raise HTTPException(status_code=404, detail=SHELVED_DETAIL)
    return closed
