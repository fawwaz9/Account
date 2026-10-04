from enum import Enum

from pydantic import BaseModel


class Module(str, Enum):
    """The rooms, as the sidebar names them. What a visit is a visit to."""

    DASHBOARD = "dashboard"
    GRADES = "grades"
    CALENDAR = "calendar"
    TASKS = "tasks"
    JOBS = "jobs"
    BUDGET = "budget"
    SETTINGS = "settings"


class VisitCreate(BaseModel):
    module: Module
