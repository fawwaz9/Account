import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    calendar, finances, grades, omnibox, recurring, tasks, users, auth,
)
from app._database.db import Base, engine
from app._database import models
from app._database.migrations import ensure_schema

# The audit log needs somewhere to go. uvicorn configures its own loggers but not
# the application's, so without this every audit.* call is swallowed by the root
# logger's default WARNING threshold and successful sign-ins are never recorded.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
)

app = FastAPI()
Base.metadata.create_all(bind=engine)
ensure_schema()

allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(grades.router, prefix="/api/grades", tags=["Grades"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(calendar.router, prefix="/api/calendar", tags=["Calendar"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(finances.router, prefix="/api/finances", tags=["Finances"])
# Same prefix as finances: a standing instruction is a money concept, and the
# client should not have to know it lives in its own module.
app.include_router(recurring.router, prefix="/api/finances", tags=["Recurring"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
# One input for every module, so it sits above all of them rather than inside
# any one.
app.include_router(omnibox.router, prefix="/api/omnibox", tags=["Omnibox"])