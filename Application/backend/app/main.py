from fastapi import FastAPI
from app.api.routes import calender, finances, grades, tasks, users

app = FastAPI()
api = "/api/users"

app.include_router(grades.router, prefix=api, tags=["Grades"])
app.include_router(users.router, prefix=api, tags=["Users"])
app.include_router(calender.router, prefix=api, tags=["Calendar"])
app.include_router(tasks.router, prefix=api, tags=["Tasks"])
app.include_router(finances.router, prefix=api, tags=["Finances"])
