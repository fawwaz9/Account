import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    calendar, finances, grades, jobs, omnibox, recurring, tasks, users, auth,
)
from app._database.db import Base, engine
from app._database import models
from app._database.migrations import ensure_indexes, ensure_schema

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
    yield


app = FastAPI(lifespan=lifespan)

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