import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes import (
    calendar, finances, grades, jobs, omnibox, recurring, tasks, users, auth,
)
from app._database.db import Base, SessionLocal, engine
from app._database import models
from app._database.migrations import ensure_indexes, ensure_schema
from app.Users.services.user_service import purge_expired_users

# The audit log needs somewhere to go. uvicorn configures its own loggers but not
# the application's, so without this every audit.* call is swallowed by the root
# logger's default WARNING threshold and successful sign-ins are never recorded.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Bring the schema up to date, once, when the server actually starts.

    Deliberately not at module import. These three issue DDL, and `import
    app.main` happens in places that are emphatically not a server start: a
    test collector, a reload worker, an IDE indexer, `--help`. Any of those
    would write to whatever `DATABASE_URL` happened to point at.
    """
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    ensure_indexes()

    # Accounts whose grace period has run out. No scheduler in this app, so it
    # runs here for the same reason due payments are written on read: idempotent
    # work, done when something is already happening. A machine left off for a
    # month catches up the moment it starts, which is the correct outcome --
    # the deadline passed whether or not the server was running.
    with SessionLocal() as session:
        purged = purge_expired_users(session)
    if purged:
        logging.getLogger("audit").info("purged %s expired account(s)", purged)

    yield


#: Whether the interactive docs are served. **Off unless asked for**, which is
#: the opposite of FastAPI's default and the opposite of what this app did: all
#: three endpoints were public, publishing every route, parameter and schema to
#: anyone who looked. Defaulting to off means a forgotten variable hides them
#: rather than exposing them -- the failure that costs nothing, instead of the
#: one nobody notices.
DOCS_ENABLED = os.getenv("ENABLE_DOCS", "").strip().lower() in {"1", "true", "yes", "on"}

app = FastAPI(
    lifespan=lifespan,
    docs_url="/docs" if DOCS_ENABLED else None,
    redoc_url="/redoc" if DOCS_ENABLED else None,
    # Turned off with them: leaving the schema served is leaving the docs
    # served, since the pages are only a renderer for this.
    openapi_url="/openapi.json" if DOCS_ENABLED else None,
)


@app.get("/health", include_in_schema=False)
def health(response: Response):
    """Is this process able to do its job, rather than merely running?

    Answers with the database, not just with itself. A check that only proves
    uvicorn is listening reports healthy while every real request fails on a
    dead connection -- which, with a database that suspends when idle and a
    container that is torn down and recreated constantly, is the most likely
    way this deployment breaks. A probe that cannot see the dependency it is
    worried about is decoration.

    503 rather than an exception, so a monitor reads a status code instead of a
    stack trace, and so the body can say which half is unwell.
    """
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - any failure to reach it is unhealthy
        logging.getLogger("app.health").warning("health check failed: %s", exc)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unhealthy", "database": "unreachable"}

    return {"status": "ok", "database": "ok"}

# Stripped, because "a.com, b.com" is the natural way to write a list and the
# space made the second entry " b.com", which no Origin header can ever equal --
# a silently unreachable origin rather than a visible misconfiguration.
allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    # Authentication is a Bearer header that the client sets on each request,
    # and no cookie is ever set, so credentialed CORS grants nothing today. It
    # only widens what a future wrong ALLOWED_ORIGINS would expose.
    allow_credentials=False,
    # The methods and headers the API actually uses, rather than "*". A wildcard
    # permits verbs no route serves and headers nothing reads.
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(grades.router, prefix="/api/grades", tags=["Grades"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(calendar.router, prefix="/api/calendar", tags=["Calendar"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["Jobs"])
app.include_router(finances.router, prefix="/api/finances", tags=["Finances"])
# Same prefix as finances: a standing instruction is a money concept, and the
# client should not have to know it lives in its own module.
app.include_router(recurring.router, prefix="/api/finances", tags=["Recurring"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
# One input for every module, so it sits above all of them rather than inside
# any one.
app.include_router(omnibox.router, prefix="/api/omnibox", tags=["Omnibox"])