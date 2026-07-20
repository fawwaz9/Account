from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import calender, finances, grades, tasks, users

app = FastAPI()

app.add_middleware(
    CORSMiddleware, 
    allow_origins=[
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = "/api/users"

app.include_router(grades.router, prefix=api, tags=["Grades"])
app.include_router(users.router, prefix=api, tags=["Users"])
app.include_router(calender.router, prefix=api, tags=["Calendar"])
app.include_router(tasks.router, prefix=api, tags=["Tasks"])
app.include_router(finances.router, prefix=api, tags=["Finances"])
