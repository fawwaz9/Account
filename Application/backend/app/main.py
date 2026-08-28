import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import calender, finances, grades, tasks, users, auth
from app._database.db import Base, engine
from app._database import models

app = FastAPI()
Base.metadata.create_all(bind=engine)

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
app.include_router(calender.router, prefix="/api/calendar", tags=["Calendar"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(finances.router, prefix="/api/finances", tags=["Finances"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])