"""Bringing the database's shape up to date, as a thing you run.

This used to happen only inside the application's startup hook, which made it
invisible: there was no way to update the schema without starting a server, and
no way to start a server without updating the schema. On a host that scales to
zero, that second half is the expensive one -- the work is repeated on every
cold start to re-establish something that has not changed since the last deploy.

So it lives here, callable two ways:

    python -m app._database.schema      # as a deploy step
    apply_schema()                      # from the lifespan, when asked

Idempotent either way, which is what makes it safe to run as often as you like
and safe to leave out of startup entirely.
"""
import logging
import time

from app._database.db import Base, engine
from app._database import models  # noqa: F401 - populates Base.metadata
from app._database.migrations import ensure_indexes, ensure_schema

logger = logging.getLogger("app.schema")


def apply_schema() -> float:
    """Create missing tables, add missing columns, create missing indexes.

    Returns how long it took, in seconds. Reported rather than discarded
    because this is the work that was quietly on the critical path of every
    request after an idle period, and a number makes that visible.
    """
    started = time.monotonic()

    Base.metadata.create_all(bind=engine)
    ensure_schema()
    ensure_indexes()

    elapsed = time.monotonic() - started
    logger.info("schema up to date in %.2fs", elapsed)
    return elapsed


if __name__ == "__main__":
    logging.basicConfig(level="INFO", format="%(levelname)-8s %(name)s %(message)s")
    logger.info("applying schema to %s", engine.url.render_as_string(hide_password=True))
    apply_schema()
