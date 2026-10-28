"""Bring the database's schema up to date, as a deploy step or from app startup.

Run `python -m app._database.schema` against a database to create missing tables,
add missing columns and indexes, and install row security; the app's lifespan calls
`apply_schema` itself only when `RUN_SCHEMA_ON_STARTUP` asks it to. Every step is
idempotent, so running it again is harmless.
"""
import logging
import time

from app._database.db import Base, engine
from app._database import models  # noqa: F401 - populates Base.metadata
from app._database.migrations import ensure_indexes, ensure_schema
from app._database import rls

logger = logging.getLogger("app.schema")


def apply_schema() -> float:
    """Create missing tables, columns and indexes, then install row security.

    Runs `create_all`, `ensure_schema`, `ensure_indexes` and `rls.install` in that
    order on the application engine, each step committing on its own; a failed run can
    simply be repeated.

    Returns:
        How long the whole run took, in seconds.
    """
    started = time.monotonic()

    Base.metadata.create_all(bind=engine)
    ensure_schema()
    ensure_indexes()
    # Row-level security functions, and the policies once the app role exists.
    # A no-op on SQLite. Last, because the policies are written per table.
    rls.install(engine)

    elapsed = time.monotonic() - started
    logger.info("schema up to date in %.2fs", elapsed)
    return elapsed


if __name__ == "__main__":
    logging.basicConfig(level="INFO", format="%(levelname)-8s %(name)s %(message)s")
    logger.info("applying schema to %s", engine.url.render_as_string(hide_password=True))
    apply_schema()
